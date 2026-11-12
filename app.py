"""
Streamlit Web Application: Video Content & Copyright Reviewer
Tích hợp:
1. Trích xuất Keyframe thông minh & Lọc mờ/tối
2. Kiểm tra thị giác kiểu Google Lens & Soi Watermark/Re-up (Gemini Vision)
3. Phân tích kịch bản, ý tưởng & Sinh Search Queries (Gemini Flash)
4. Quét đối thủ cạnh tranh trên YouTube (yt-dlp) & Facebook
5. Báo cáo đánh giá độ trùng lặp & Lời khuyên tối ưu nội dung
"""

import os
import sys
import shutil
import tempfile
import concurrent.futures
import streamlit as st
import yt_dlp
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

from modules import create_gemini_client
from modules.keyframe_extractor import extract_smart_keyframes, trim_video_fast
from modules.visual_search import (
    analyze_keyframes_with_gemini,
    search_google_lens_serpapi,
    generate_reverse_search_urls
)
from modules.content_analyzer import analyze_video_content
from modules.platform_search import (
    search_multiple_queries_youtube,
    search_multiple_queries_facebook,
    generate_facebook_search_links
)
from modules.duplicate_evaluator import evaluate_video_report
from modules.url_downloader import download_video_from_url, clean_extract_url, detect_platform_from_url, normalize_url

# Console Windows mặc định cp1252 sẽ ném UnicodeEncodeError khi in tiếng Việt ra file redirect.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None:
        _stream.reconfigure(encoding="utf-8", errors="replace")


st.set_page_config(
    page_title="AI Video Content & Copyright Reviewer",
    page_icon="🎬",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #4B5563;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .competitor-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-youtube {
        background: #EF4444;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.75rem;
        display: inline-block;
        margin-bottom: 5px;
    }
    .badge-facebook {
        background: #1877F2;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.75rem;
        display: inline-block;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Khởi tạo thư mục làm việc cố định trong phiên
if "work_dir" not in st.session_state:
    st.session_state["work_dir"] = tempfile.mkdtemp()
temp_dir = st.session_state["work_dir"]


def _is_loopback_binding() -> bool:
    # Chỉ tự điền API key từ .env khi server bind loopback; bind LAN (0.0.0.0) thì không
    # để key không bị lộ cho thiết bị khác trong mạng dùng chung giao diện.
    addr = st.config.get_option("server.address")
    if not addr:
        return False
    addr = str(addr).strip().strip("[]").lower()
    return addr in ("localhost", "::1") or addr.startswith("127.")


_prefill_keys = _is_loopback_binding()

# Sidebar cấu hình
with st.sidebar:
    st.header("⚙️ Cấu hình API")
    if not _prefill_keys:
        st.caption("🔒 Đang mở cho mạng LAN: vì bảo mật, API key không tự điền sẵn. Vui lòng nhập key mỗi phiên (key chỉ nằm trong trình duyệt của bạn, không gửi cho thiết bị khác).")
    gemini_key = st.text_input(
        "Google Gemini API Key",
        value=os.environ.get("GEMINI_API_KEY", "") if _prefill_keys else "",
        type="password",
        help="Nhập API Key từ Google AI Studio (aistudio.google.com)"
    )

    serpapi_key = st.text_input(
        "SerpApi Key (Google Lens - Tùy chọn)",
        value=os.environ.get("SERPAPI_API_KEY", "") if _prefill_keys else "",
        type="password",
        help="Dùng để tự động quét Google Lens. Nếu không có, tool vẫn hỗ trợ link tra cứu trực tiếp."
    )
    
    st.markdown("---")
    st.header("🧪 Chế độ thử nghiệm")
    demo_mode = st.checkbox("Chế độ Demo (Test không cần API Key)", value=False, help="Cho phép test toàn bộ quy trình bóc tách hình ảnh, quét đối thủ YouTube và giao diện ngay cả khi chưa có Gemini Key.")
    
    st.markdown("---")
    st.header("⚡ Tốc độ & Phạm vi quét")
    scan_scope = st.radio(
        "Thời lượng quét tối ưu:",
        options=[
            "⚡ Siêu tốc: 15 giây đầu (Hook & Intro - Khuyên dùng)",
            "⏱️ Nhanh: 30 giây đầu",
            "🎬 Trung bình: 60 giây đầu",
            "🎞️ Toàn bộ video (Quét sâu)"
        ],
        index=0,
        help="90% video TikTok/Reels chỉ cần soi 15s đầu là đã biết nguồn gốc, kịch bản Hook và đối thủ, giúp giảm thời gian quét từ 1 phút xuống còn 10-15 giây!"
    )
    
    st.markdown("---")
    st.header("🎛️ Tùy chọn nâng cao")
    max_keyframes = st.slider("Số lượng Keyframes cần bóc tách", min_value=3, max_value=8, value=4)
    selected_model = st.selectbox(
        "Mô hình Gemini",
        options=["gemini-3.8-flash", "gemini-3.5-flash-lite"],
        index=0
    )
    
    if st.button("🗑️ Xóa kết quả & Làm mới"):
        if "analysis_results" in st.session_state:
            del st.session_state["analysis_results"]
        if "downloaded_video_path" in st.session_state:
            del st.session_state["downloaded_video_path"]
        st.rerun()


# Tiêu đề ứng dụng
st.markdown('<div class="main-title">🎬 AI Video Content & Copyright Reviewer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Xem, review nội dung video, soi nguồn gốc kiểu Google Lens và quét tìm kiếm đối thủ trên YouTube / Facebook xem đã có ai làm chưa.</div>', unsafe_allow_html=True)


# Tùy chọn đầu vào: Upload file hoặc Dán Link
input_method = st.radio(
    "Chọn nguồn video:",
    ["📤 Tải lên file video (MP4, MOV, MKV)", "🔗 Dán link video (YouTube, Douyin, TikTok, Facebook)"],
    horizontal=True
)

video_path = None
clean_url = ""
platform_detected = ""

if input_method.startswith("📤"):
    uploaded_file = st.file_uploader("Kéo thả hoặc chọn file video", type=["mp4", "mov", "mkv", "webm"])
    if uploaded_file:
        ext = os.path.splitext(uploaded_file.name)[1] or ".mp4"
        safe_name = f"uploaded_video{ext}"
        video_path = os.path.join(temp_dir, safe_name)
        with open(video_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.video(video_path)
else:
    st.markdown("""
    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.9rem;">
        <b>Hỗ trợ đa nền tảng:</b> 
        <span style="color: #EF4444; font-weight: bold;">📺 YouTube</span> • 
        <span style="color: #000000; font-weight: bold;">🎵 TikTok</span> • 
        <span style="color: #10B981; font-weight: bold;">🇨🇳 Douyin (抖音)</span> • 
        <span style="color: #1877F2; font-weight: bold;">📘 Facebook Reels & Watch</span>
        <br><span style="color: #64748B; font-size: 0.82rem;">💡 Mẹo: Bạn có thể dán nguyên cả đoạn văn bản chia sẻ từ app Douyin/TikTok, tool sẽ tự động bóc tách link sạch!</span>
    </div>
    """, unsafe_allow_html=True)
    
    video_url_input = st.text_input(
        "Dán link video hoặc nội dung chia sẻ:",
        placeholder="Ví dụ: https://v.douyin.com/... hoặc https://vt.tiktok.com/... hoặc https://youtu.be/..."
    )
    
    if video_url_input:
        clean_url = clean_extract_url(video_url_input)
        if clean_url:
            platform_detected = detect_platform_from_url(clean_url)
            st.caption(f"🎯 Phát hiện nền tảng: **{platform_detected}** | Link: `{clean_url}`")
            
            # Nếu người dùng đổi sang link mới, tự động hủy cache video cũ
            if st.session_state.get("downloaded_for_url") and st.session_state.get("downloaded_for_url") != clean_url:
                if "downloaded_video_path" in st.session_state:
                    del st.session_state["downloaded_video_path"]
                if "downloaded_video_info" in st.session_state:
                    del st.session_state["downloaded_video_info"]
                if "analysis_results" in st.session_state:
                    del st.session_state["analysis_results"]
                st.session_state["downloaded_for_url"] = clean_url
            
            if st.button("📥 Tải trước video để xem thử"):
                with st.spinner(f"Đang kết nối & tải video từ {platform_detected}..."):
                    try:
                        res = download_video_from_url(clean_url, temp_dir)
                        st.session_state["downloaded_video_path"] = res["video_path"]
                        st.session_state["downloaded_video_info"] = res
                        st.session_state["downloaded_for_url"] = clean_url
                        st.success(f"Tải video thành công từ {platform_detected}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"{e}")

if "downloaded_video_path" in st.session_state and os.path.exists(st.session_state["downloaded_video_path"]):
    video_path = st.session_state["downloaded_video_path"]
    if not input_method.startswith("📤"):
        st.video(video_path)


# Nút bắt đầu phân tích (Hỗ trợ bấm quét ngay cả khi chưa bấm nút tải trước)
can_start_analysis = (video_path and os.path.exists(video_path)) or (not input_method.startswith("📤") and clean_url)

if can_start_analysis:
    st.markdown("---")
    if st.button("🚀 BẮT ĐẦU QUÉT & REVIEW TOÀN DIỆN", type="primary", use_container_width=True):
        if not gemini_key and not demo_mode:
            st.error("⚠️ Vui lòng nhập Gemini API Key ở thanh bên trái (Sidebar) hoặc tích chọn 'Chế độ Demo' để thử nghiệm.")
            st.stop()
            
        progress_bar = st.progress(0, text="Bắt đầu phân tích...")
        
        # Nếu người dùng chưa bấm tải trước mà bấm Quét luôn, tự động tải ngay
        if (not video_path or not os.path.exists(video_path)) and clean_url:
            progress_bar.progress(5, text=f"📥 Đang tự động kết nối & tải video từ {platform_detected}...")
            try:
                res = download_video_from_url(clean_url, temp_dir)
                video_path = res["video_path"]
                st.session_state["downloaded_video_path"] = video_path
                st.session_state["downloaded_video_info"] = res
                st.session_state["downloaded_for_url"] = clean_url
            except Exception as e:
                st.error(f"{e}")
                st.stop()
        
        max_duration_sec = 15
        if "30 giây" in scan_scope:
            max_duration_sec = 30
        elif "60 giây" in scan_scope:
            max_duration_sec = 60
        elif "Toàn bộ" in scan_scope:
            max_duration_sec = None

        try:
            # 1. Cắt nhanh N giây đầu tiên nếu được chọn (giảm dung lượng xuống còn vài MB, tăng tốc 5x)
            target_video_to_process = video_path
            if max_duration_sec:
                progress_bar.progress(10, text=f"⚡ Đang cắt nhanh {max_duration_sec}s đầu (Hook & Intro) để tăng tốc...")
                trimmed_video_path = os.path.join(temp_dir, f"trimmed_{max_duration_sec}s.mp4")
                target_video_to_process = trim_video_fast(video_path, trimmed_video_path, max_duration_sec=max_duration_sec)

            # 2. Bóc tách Keyframes thật từ phân đoạn được chọn
            progress_bar.progress(25, text="📸 Đang trích xuất Keyframes thông minh & lọc mờ/tối...")
            keyframes_dir = os.path.join(temp_dir, "keyframes")
            keyframes = extract_smart_keyframes(target_video_to_process, keyframes_dir, max_frames=max_keyframes)
            keyframe_paths = [k['path'] for k in keyframes]
            
            # 3. Xử lý phân tích thị giác & kịch bản song song (AI Parallel Processing)
            if demo_mode and not gemini_key:
                progress_bar.progress(50, text="🧪 [Demo] Mô phỏng phản hồi AI thẩm định...")
                visual_data = {
                    "assessment_markdown": """
                **[Demo Mode] Đánh giá thị giác:**
                - Khung hình rõ nét, ánh sáng tự nhiên.
                - Không phát hiện watermark cứng (hardcoded logo) từ Douyin hoặc TikTok.
                - Khung cảnh mang phong cách video tự quay đời thường (Original vlog/review).
                - Tỷ lệ phán đoán: 85% Video gốc tự sản xuất, 15% khả năng trích xuất tư liệu.
                """,
                    "verdict": "original",
                    "reup_confidence": 0,
                    "watermarks_found": [],
                }
                content_data = {
                    "title_suggestion": "Review trải nghiệm thực tế sản phẩm công nghệ",
                    "topic_category": "Công nghệ / Tiêu dùng",
                    "hook_analysis": "Mở đầu trực diện với câu hỏi đánh vào điểm đau của người dùng.",
                    "summary": "Video chia sẻ trải nghiệm thực tế, phân tích ưu nhược điểm và đưa ra lời khuyên mua sắm hữu ích cho người xem.",
                    "script_breakdown": [
                        {"timestamp": "00:00", "content": "Mở đầu nêu vấn đề và sản phẩm trải nghiệm"},
                        {"timestamp": "00:20", "content": "Đi sâu vào tính năng chính và so sánh"},
                        {"timestamp": "00:45", "content": "Tổng kết đánh giá và kết luận"}
                    ],
                    "core_idea": "Review công nghệ thực tế đời sống",
                    "youtube_queries": ["review công nghệ đời sống", "trải nghiệm sản phẩm thực tế"],
                    "facebook_queries": ["review công nghệ", "đồ chơi công nghệ"],
                    "originality_assessment": "Chủ đề quen thuộc nhưng góc quay và cách trình bày mang phong cách cá nhân.",
                    "estimated_originality_score": 78
                }
                lens_matches = []
            else:
                client = create_gemini_client(gemini_key)
                progress_bar.progress(50, text="⚡ AI đang phân tích song song hình ảnh & kịch bản (Tăng tốc độ)...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    future_visual = executor.submit(analyze_keyframes_with_gemini, client, keyframe_paths, selected_model)
                    future_content = executor.submit(analyze_video_content, client, target_video_to_process, keyframe_paths, selected_model)
                    future_lens = None
                    if serpapi_key and keyframe_paths:
                        future_lens = executor.submit(search_google_lens_serpapi, keyframe_paths[0], serpapi_key)
                        
                    visual_data = future_visual.result()
                    content_data = future_content.result()
                    lens_matches = future_lens.result() if future_lens else []
            
            # 3. Quét đối thủ THẬT trên YouTube & Facebook (chạy song song)
            progress_bar.progress(80, text="🔎 Đang tìm kiếm các video tương tự trên YouTube & Facebook...")
            yt_queries = content_data.get("youtube_queries", [])
            fb_queries = content_data.get("facebook_queries", [])
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_yt = executor.submit(search_multiple_queries_youtube, yt_queries, 3)
                future_fb = executor.submit(search_multiple_queries_facebook, fb_queries, 3)
                
                yt_scan = future_yt.result()
                youtube_results = yt_scan["videos"]
                facebook_results = future_fb.result()
            
            # 4. Tạo đường link tìm kiếm nâng cao cho Facebook
            fb_targets = generate_facebook_search_links(fb_queries)
            
            # 5. Đánh giá tổng hợp
            progress_bar.progress(95, text="📊 Đang tổng hợp báo cáo đánh giá bản quyền & độ độc đáo...")
            report = evaluate_video_report(visual_data, content_data, youtube_results, lens_matches, youtube_scan_ok=yt_scan["ok"], facebook_results=facebook_results)
            
            # Lưu kết quả vào session_state để không bị mất khi chuyển tab
            st.session_state["analysis_results"] = {
                "report": report,
                "keyframes": keyframes,
                "visual_data": visual_data,
                "lens_matches": lens_matches,
                "content_data": content_data,
                "youtube_results": youtube_results,
                "facebook_results": facebook_results,
                "fb_targets": fb_targets
            }
            
            progress_bar.progress(100, text="✅ Hoàn tất!")
            st.success("Đã hoàn thành kiểm tra và đánh giá toàn diện!")
            
        except Exception as err:
            st.error(f"Đã có lỗi xảy ra trong quá trình xử lý: {err}")


# HIỂN THỊ KẾT QUẢ TỪ SESSION STATE (Đảm bảo không bị mất khi click qua lại giữa các tab)
if "analysis_results" in st.session_state:
    res = st.session_state["analysis_results"]
    report = res["report"]
    keyframes = res["keyframes"]
    visual_data = res["visual_data"]
    lens_matches = res["lens_matches"]
    content_data = res["content_data"]
    youtube_results = res["youtube_results"]
    facebook_results = res.get("facebook_results", [])
    fb_targets = res["fb_targets"]
    
    st.markdown("---")
    tab_report, tab_visual, tab_content, tab_competitors = st.tabs([
        "📊 Báo Cáo Tổng Hợp",
        "👁️ Tầng 1: Soi Hình Ảnh (Google Lens)",
        "🧠 Tầng 2: Kịch Bản & Ý Tưởng",
        "🔍 Đối Thủ YouTube & Facebook"
    ])
    
    # TAB 1: BÁO CÁO TỔNG HỢP
    with tab_report:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="Điểm độc đáo ý tưởng", value=f"{report['originality_score']}/100")
        with col2:
            st.metric(label="Nguy cơ Re-up hình ảnh", value=report['reup_risk'].split('(')[0].strip())
        with col3:
            st.metric(label="Số đối thủ quét được (YouTube + Facebook)", value=f"{report['competitor_count']} video")
            
        st.markdown("### 💡 Lời khuyên chiến lược cho bạn:")
        for rec in report['recommendations']:
            st.markdown(rec)
            
        st.markdown("### 📌 Tóm tắt định vị:")
        st.info(f"**Chủ đề:** {content_data.get('topic_category', 'N/A')}  \n**Mức độ cạnh tranh:** {report['saturation_level']}")

    # TAB 2: VISUAL SEARCH
    with tab_visual:
        st.subheader("🖼️ Khung hình tiêu biểu (Keyframes đã lọc mờ/tối)")
        if keyframes:
            cols = st.columns(len(keyframes))
            for idx, (col, kf) in enumerate(zip(cols, keyframes)):
                with col:
                    st.image(kf['path'], caption=f"Khung hình {idx+1} ({kf['timestamp_str']})")
                
        st.markdown("### 🔬 Đánh giá thị giác & Dấu vết Re-up (Gemini Vision):")
        st.markdown(visual_data["assessment_markdown"])
        
        st.markdown("### 🌐 Tra cứu ngược hình ảnh (Reverse Visual Search):")
        st.markdown("Bấm vào các nút dưới đây để mở công cụ tra cứu ngay trên trình duyệt:")
        search_links = generate_reverse_search_urls(content_data.get("core_idea", "video"))
        link_cols = st.columns(len(search_links))
        for col, (name, link) in zip(link_cols, search_links.items()):
            col.markdown(f"[{name}]({link})")
            
        if lens_matches:
            st.markdown("#### 🎯 Kết quả Google Lens trực tiếp (Visual Matches):")
            lens_cols = st.columns(2)
            for idx, m in enumerate(lens_matches):
                with lens_cols[idx % 2]:
                    with st.container(border=True):
                        if m.get("thumbnail"):
                            st.image(m["thumbnail"], use_container_width=True)
                        st.markdown(f"**[{m['title']}]({m['link']})**")
                        st.caption(f"🌐 Nguồn: **{m.get('source', 'Web')}**")
                        st.link_button("👉 Xem nguồn gốc", m["link"], use_container_width=True)

    # TAB 3: CONTENT & SCRIPT
    with tab_content:
        st.subheader("📝 Phân tích kịch bản & Ý tưởng")
        st.markdown(f"**Tiêu đề đề xuất:** {content_data.get('title_suggestion', 'N/A')}")
        st.markdown(f"**Tóm tắt nội dung:** {content_data.get('summary', 'N/A')}")
        st.markdown(f"**Hook 3 giây đầu:** {content_data.get('hook_analysis', 'N/A')}")
        
        script_breakdown = content_data.get('script_breakdown', [])
        if script_breakdown:
            st.markdown("#### ⏱️ Dàn ý phân đoạn kịch bản:")
            for s in script_breakdown:
                st.markdown(f"- **`{s.get('timestamp', '')}`**: {s.get('content', '')}")
                
        st.markdown(f"**Đánh giá độ mới:** {content_data.get('originality_assessment', 'N/A')}")

    # TAB 4: COMPETITORS (Visual Cards like Google Lens)
    with tab_competitors:
        st.subheader("🔍 Danh Sách Đối Thủ Trực Quan (YouTube & Facebook)")
        st.markdown("Hiển thị chi tiết theo phong cách Google Lens: **Ảnh thumbnail, Nguồn, Nền tảng, Lượt xem và Link xem trực tiếp**.")
        
        # Tùy chọn lọc nền tảng
        platform_filter = st.radio(
            "Lọc theo nền tảng:",
            ["Tất cả nền tảng", "🔴 YouTube", "🔵 Facebook"],
            horizontal=True
        )
        
        combined_competitors = []
        if platform_filter in ("Tất cả nền tảng", "🔴 YouTube"):
            combined_competitors.extend(youtube_results or [])
        if platform_filter in ("Tất cả nền tảng", "🔵 Facebook"):
            combined_competitors.extend(facebook_results or [])
            
        if combined_competitors:
            st.markdown(f"🔥 **Phát hiện {len(combined_competitors)} nội dung đối thủ:**")
            
            # Hiển thị thẻ dạng lưới trực quan 2 cột
            cols = st.columns(2)
            for idx, item in enumerate(combined_competitors):
                col = cols[idx % 2]
                with col:
                    with st.container(border=True):
                        # 1. Ảnh Thumbnail (không dùng ảnh stock thay cho ảnh thật của video)
                        if item.get("thumbnail"):
                            st.image(item["thumbnail"], use_container_width=True)
                        else:
                            st.caption("Không có ảnh xem trước cho video này.")
                        
                        # 2. Badge Nền tảng
                        if item.get("platform") == "YouTube":
                            st.markdown('<span class="badge-youtube">🔴 YOUTUBE</span>', unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="badge-facebook">🔵 FACEBOOK WATCH</span>', unsafe_allow_html=True)
                            
                        # 3. Tiêu đề
                        st.markdown(f"#### [{item['title']}]({item['url']})")
                        
                        # 4. Thông tin chi tiết (Kênh, view, thời lượng, ngày đăng)
                        uploader = item.get('uploader', 'N/A')
                        views = item.get('views', 'N/A')
                        duration = item.get('duration', 'N/A')
                        date = item.get('date', 'N/A')
                        st.caption(f"👤 **Kênh / Nguồn:** `{uploader}`  \n👁️ **Lượt xem:** {views} • ⏱️ **Thời lượng:** {duration} • 📅 **Đăng:** {date}")
                        
                        # 5. Nút mở xem video
                        st.link_button(f"👉 Mở xem video trên {item.get('platform')}", item['url'], use_container_width=True)
        else:
            st.info("Chưa tìm thấy video đối thủ phù hợp với bộ lọc đã chọn.")
            
        st.markdown("---")
        st.markdown("### 📘 Tra cứu nhanh mở rộng trên Facebook (Watch & Reels):")
        for fb in fb_targets:
            st.markdown(f"- **Từ khóa:** `{fb['query']}`  \n  [👉 Xem trực tiếp trên Facebook Watch]({fb['watch_url']}) | [👉 Tìm Google Facebook Reels]({fb['google_dork_reels']})")
