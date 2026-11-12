"""
CLI Tool: video_checker.py
Giao diện dòng lệnh để quét và review video nhanh chóng từ terminal.

Cách dùng:
    python cli.py --video "duong_dan_video.mp4"
    python cli.py --url "https://www.tiktok.com/@.../video/..."
"""

import os
import sys
import argparse
import logging
import tempfile
import yt_dlp
from dotenv import load_dotenv

from modules import create_gemini_client
from modules.keyframe_extractor import extract_smart_keyframes
from modules.visual_search import analyze_keyframes_with_gemini, search_google_lens_serpapi
from modules.content_analyzer import analyze_video_content
from modules.platform_search import search_multiple_queries_youtube, generate_facebook_search_links
from modules.duplicate_evaluator import evaluate_video_report

# Console Windows mặc định cp1252 sẽ ném UnicodeEncodeError khi in tiếng Việt ra file redirect.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None:
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="AI Video Content & Copyright Reviewer CLI")
    parser.add_argument("--video", type=str, help="Đường dẫn đến file video MP4 trên máy")
    parser.add_argument("--url", type=str, help="Đường dẫn URL video từ TikTok/YouTube/Facebook")
    parser.add_argument("--gemini-key", type=str, default=os.environ.get("GEMINI_API_KEY"), help="Gemini API Key")
    parser.add_argument("--serpapi-key", type=str, default=os.environ.get("SERPAPI_API_KEY"), help="SerpApi Key (Google Lens)")
    parser.add_argument("--keyframes", type=int, default=5, help="Số khung hình cần trích xuất (mặc định: 5)")
    
    args = parser.parse_args()
    
    if not args.video and not args.url:
        print("Lỗi: Vui lòng cung cấp --video hoặc --url")
        sys.exit(1)
        
    if not args.gemini_key:
        print("Lỗi: Vui lòng cấu hình GEMINI_API_KEY qua biến môi trường hoặc tham số --gemini-key")
        sys.exit(1)
        
    temp_dir = tempfile.mkdtemp()
    target_video_path = args.video
    
    if args.url:
        print(f"[*] Đang tải video từ URL: {args.url}...")
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, 'input_video.%(ext)s'),
            'format': 'mp4/best[height<=720]',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(args.url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                filename = os.path.splitext(filename)[0] + ".mp4"
            target_video_path = filename
            
    print(f"[*] Đang xử lý video: {target_video_path}")
    
    # 1. Trích xuất keyframes
    print("[1/5] Trích xuất khung hình thông minh...")
    kf_dir = os.path.join(temp_dir, "keyframes")
    keyframes = extract_smart_keyframes(target_video_path, kf_dir, max_frames=args.keyframes)
    kf_paths = [k['path'] for k in keyframes]
    print(f"      Đã lưu {len(keyframes)} khung hình tiêu biểu vào: {kf_dir}")
    
    # 2. Khởi tạo Gemini
    client = create_gemini_client(args.gemini_key)
    
    # 3. Phân tích thị giác
    print("[2/5] Soi hình ảnh & phát hiện dấu vết Re-up (Gemini Vision)...")
    visual_data = analyze_keyframes_with_gemini(client, kf_paths)
    
    lens_matches = []
    if args.serpapi_key and kf_paths:
        print("[*] Đang tra cứu Google Lens qua SerpApi...")
        lens_matches = search_google_lens_serpapi(kf_paths[0], args.serpapi_key)
        
    # 4. Phân tích kịch bản
    print("[3/5] Phân tích kịch bản, ý tưởng & tạo bộ từ khóa...")
    content_data = analyze_video_content(client, target_video_path, kf_paths)
    
    # 5. Quét đối thủ YouTube & Facebook
    print("[4/5] Quét đối thủ trên YouTube...")
    yt_queries = content_data.get("youtube_queries", [])
    yt_scan = search_multiple_queries_youtube(yt_queries, max_per_query=3)
    youtube_results = yt_scan["videos"]
    fb_targets = generate_facebook_search_links(content_data.get("facebook_queries", []))
    
    # 6. Đánh giá tổng hợp
    print("[5/5] Đang lập báo cáo tổng hợp...\n")
    report = evaluate_video_report(visual_data, content_data, youtube_results, lens_matches, youtube_scan_ok=yt_scan["ok"])
    
    print("=" * 60)
    print("                   BÁO CÁO REVIEW VIDEO                    ")
    print("=" * 60)
    print(f"Chủ đề: {content_data.get('topic_category')}")
    print(f"Tiêu đề tóm tắt: {content_data.get('title_suggestion')}")
    print(f"Điểm độc đáo: {report['originality_score']}/100")
    print(f"Nguy cơ Re-up: {report['reup_risk']}")
    print(f"Mức độ bão hòa: {report['saturation_level']}")
    print("-" * 60)
    print("KỊCH BẢN & Ý TƯỞNG CỐT LÕI:")
    print(f"• Tóm tắt: {content_data.get('summary')}")
    print(f"• Hook: {content_data.get('hook_analysis')}")
    print("-" * 60)
    print(f"ĐỐI THỦ PHÁT HIỆN TRÊN YOUTUBE ({len(youtube_results)} video):")
    for idx, v in enumerate(youtube_results, start=1):
        print(f"  {idx}. {v['title']}")
        print(f"     Kênh: {v['uploader']} | Lượt xem: {v['views']} | Link: {v['url']}")
    print("-" * 60)
    print("LỜI KHUYÊN CHO BẠN:")
    for rec in report['recommendations']:
        print(f"  {rec}")
    print("=" * 60)


if __name__ == "__main__":
    main()
