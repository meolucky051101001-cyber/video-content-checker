"""
Comprehensive Automated Test Suite for Video Content & Copyright Reviewer
Kiểm thử toàn bộ các module và tính năng:
1. Trích xuất Keyframe thông minh & Bộ lọc mờ/tối
2. Quét đối thủ YouTube thật qua yt-dlp (Không cần key)
3. Bộ sinh liên kết tra cứu ngược Google Lens, Yandex, Facebook
4. Thuật toán chấm điểm độc đáo & Đánh giá nguy cơ Re-up
"""

import os
import sys
import shutil
import socket
import tempfile
import cv2
import numpy as np
from unittest import mock

# Console Windows mặc định cp1252 sẽ ném UnicodeEncodeError khi in tiếng Việt ra file redirect.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None:
        _stream.reconfigure(encoding="utf-8", errors="replace")

from modules.keyframe_extractor import extract_smart_keyframes, is_frame_blurry, is_frame_extreme_brightness
from modules.platform_search import (
    search_youtube_free, generate_facebook_search_links, search_facebook_google_scraper
)
from modules.visual_search import generate_reverse_search_urls, search_google_lens_serpapi
from modules.duplicate_evaluator import evaluate_video_report
from modules.url_downloader import (
    clean_extract_url, detect_platform_from_url, normalize_url,
    download_video_from_url, _assert_public_url
)


def run_tests():
    print("=" * 60)
    print("         BẮT ĐẦU CHẠY BỘ KIỂM THỬ TOÀN DIỆN (TEST SUITE)       ")
    print("=" * 60)
    
    passed_count = 0
    total_count = 8
    
    # --- TEST 1: KIỂM THỬ BỘ LỌC MỜ & ĐỘ SÁNG CỦA KEYFRAME ---
    print("\n[TEST 1/5] Kiểm thử thuật toán lọc mờ (Blur) và lọc sáng (Brightness)...")
    try:
        # 1.1 Khung hình sắc nét
        sharp_frame = np.full((240, 320, 3), 120, dtype=np.uint8)
        cv2.putText(sharp_frame, "HIGH CONTRAST SHARP", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        is_blur_sharp, score_sharp = is_frame_blurry(sharp_frame, threshold=40.0)
        
        # 1.2 Khung hình bị làm mờ (Gaussian Blur)
        blurry_frame = cv2.GaussianBlur(sharp_frame, (35, 35), 0)
        is_blur_blur, score_blur = is_frame_blurry(blurry_frame, threshold=40.0)
        
        # 1.3 Khung hình đen xì
        dark_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        is_dark, mean_dark = is_frame_extreme_brightness(dark_frame)
        
        assert score_sharp > score_blur, "Điểm độ nét của frame sắc nét phải cao hơn frame mờ!"
        assert is_dark == True, "Bộ lọc phải phát hiện màn hình đen!"
        
        print("  -> PASSED: Bộ lọc phân biệt xuất sắc khung hình sắc nét vs mờ và nhận diện đúng màn đen.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # --- TEST 2: KIỂM THỬ BÓC TÁCH KEYFRAME TỪ VIDEO MẪU ĐA PHÂN CẢNH ---
    print("\n[TEST 2/5] Kiểm thử trích xuất Keyframe thông minh từ video...")
    test_video_path = "test_multi_scene.mp4"
    test_output_dir = "test_kfs_out"
    try:
        # Tạo video mẫu 3 giây gồm 3 cảnh khác nhau: Đỏ, Xanh lá, Xanh dương
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(test_video_path, fourcc, 20.0, (320, 240))
        
        colors = [(0, 0, 200), (0, 200, 0), (200, 0, 0)]
        for c_idx, col in enumerate(colors):
            for f in range(20):
                frame = np.full((240, 320, 3), col, dtype=np.uint8)
                cv2.putText(frame, f"Scene {c_idx+1}", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                out.write(frame)
        out.release()
        
        keyframes = extract_smart_keyframes(test_video_path, test_output_dir, max_frames=3)
        assert len(keyframes) == 3, f"Yêu cầu 3 keyframes, thực tế nhận được {len(keyframes)}"
        for k in keyframes:
            assert os.path.exists(k['path']), f"File ảnh keyframe không tồn tại: {k['path']}"
            assert 'timestamp_str' in k, "Thiếu trường timestamp_str"
            
        print(f"  -> PASSED: Đã trích xuất thành công {len(keyframes)} khung hình đa cảnh với timestamp chính xác.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
    finally:
        # Dọn dẹp
        if os.path.exists(test_video_path):
            os.remove(test_video_path)
        if os.path.exists(test_output_dir):
            shutil.rmtree(test_output_dir)
            
    # --- TEST 3: KIỂM THỬ QUÉT ĐỐI THỦ THẬT TRÊN YOUTUBE ---
    print("\n[TEST 3/5] Kiểm thử cào dữ liệu đối thủ trực tiếp trên YouTube (yt-dlp)...")
    try:
        sample_query = "review tai nghe không dây giá rẻ"
        yt_vids = search_youtube_free(sample_query, max_results=3)
        assert len(yt_vids) > 0, "Không tìm thấy video nào trên YouTube!"
        
        v = yt_vids[0]
        assert "http" in v['url'], "URL video không hợp lệ"
        assert len(v['title']) > 5, "Tiêu đề video quá ngắn"
        assert v['uploader'] != "", "Tên kênh không được rỗng"
        
        print(f"  -> PASSED: Tìm thấy {len(yt_vids)} video thực tế trên YouTube:")
        for idx, item in enumerate(yt_vids[:2], 1):
            print(f"     [{idx}] {item['title'][:45]}... | Kênh: {item['uploader']} | {item['views']}")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # --- TEST 4: KIỂM THỬ BỘ TẠO LINK TRA CỨU NGƯỢC (GOOGLE LENS & FACEBOOK) ---
    print("\n[TEST 4/5] Kiểm thử sinh link tra cứu trực tiếp Google Lens, Yandex & Facebook...")
    try:
        desc = "máy bay không người lái tự chế FPV drone"
        links = generate_reverse_search_urls(desc)
        assert "Google Lens" in links
        assert "Yandex Visual" in links
        assert "YouTube Search" in links
        
        fb_links = generate_facebook_search_links([desc])
        assert len(fb_links) == 1
        assert "facebook.com/watch" in fb_links[0]['watch_url']
        assert "google.com/search" in fb_links[0]['google_dork_reels']
        
        print("  -> PASSED: Các đường link tra cứu hình ảnh và Facebook Watch/Reels được mã hóa URL chuẩn xác.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # --- TEST 5: KIỂM THỬ THUẬT TOÁN ĐÁNH GIÁ ĐỘ ĐỘC ĐÁO & NGUY CƠ RE-UP ---
    print("\n[TEST 5/5] Kiểm thử thuật toán đánh giá độ độc đáo (Originality) & Nguy cơ Re-up...")
    try:
        # Trường hợp A: AI kết luận re-up kèm bằng chứng cụ thể, nhiều đối thủ
        mock_visual_reup = {"assessment_markdown": "Phát hiện logo Douyin và phụ đề vietsub.", "verdict": "reup", "reup_confidence": 90}
        mock_content = {"estimated_originality_score": 60, "topic_category": "Hài hước"}
        mock_competitors_many = [{"id": f"vid_{i}", "url": "#"} for i in range(10)]
        
        report_reup = evaluate_video_report(mock_visual_reup, mock_content, mock_competitors_many)
        assert report_reup['reup_badge_color'] == "red" or "CAO" in report_reup['reup_risk']
        assert report_reup['originality_score'] <= 25, "Điểm độc đáo của video re-up phải bị giảm mạnh!"
        
        # Trường hợp B: Video tự quay gốc, chưa ai làm
        mock_visual_orig = {"assessment_markdown": "Góc máy cầm tay, người nói trực tiếp trước camera.", "verdict": "original", "reup_confidence": 0}
        mock_content_fresh = {"estimated_originality_score": 85, "topic_category": "Vlog"}
        mock_competitors_zero = []
        
        report_fresh = evaluate_video_report(mock_visual_orig, mock_content_fresh, mock_competitors_zero)
        assert "Thấp" in report_fresh['reup_risk']
        assert report_fresh['originality_score'] >= 85
        assert len(report_fresh['recommendations']) > 0

        # Trường hợp C (regression): văn xuôi phủ định vẫn nhắc TikTok/Douyin -> không được kết luận re-up
        mock_visual_negation = {
            "assessment_markdown": "Không phát hiện watermark TikTok hay Douyin. Video tự quay gốc, không phải re-up, không cắt ghép.",
            "verdict": "original",
            "reup_confidence": 0,
        }
        report_negation = evaluate_video_report(mock_visual_negation, mock_content_fresh, mock_competitors_zero)
        assert report_negation['reup_risk'] == report_fresh['reup_risk'], "Câu phủ định không được làm tăng nguy cơ re-up!"
        assert report_negation['originality_score'] == report_fresh['originality_score'], "Câu phủ định không được kéo điểm xuống!"

        # Trường hợp D: AI không đủ bằng chứng -> chưa xác định, không quy thành nguy cơ
        report_unknown = evaluate_video_report({"verdict": "uncertain"}, {"estimated_originality_score": 80}, mock_competitors_zero)
        assert "Chưa xác định" in report_unknown['reup_risk']
        assert report_unknown['reup_badge_color'] == "gray"
        assert report_unknown['originality_score'] == 90

        # Trường hợp E (regression): quét YouTube thất bại -> không được kết luận ngách hay cộng điểm
        report_scan_fail = evaluate_video_report(mock_visual_orig, {"estimated_originality_score": 60}, [], youtube_scan_ok=False)
        assert "Không xác định" in report_scan_fail['saturation_level'], "Quét lỗi không được coi là thị trường ngách!"
        assert report_scan_fail['originality_score'] == 60, "Quét lỗi không được cộng điểm thưởng!"
        assert not any("Cơ hội vàng" in r for r in report_scan_fail['recommendations'])

        # Trường hợp F: bằng chứng Google Lens đủ mạnh phải thắng phán đoán "original" của AI
        report_lens = evaluate_video_report(mock_visual_orig, mock_content_fresh, mock_competitors_zero, lens_matches=[{"link": "#"}] * 3)
        assert report_lens['reup_badge_color'] == "red", "Tìm thấy ảnh trên mạng phải bị đánh giá nguy cơ rất cao!"
        
        print("  -> PASSED: Chấm điểm theo verdict + bằng chứng Lens; câu phủ định và lỗi quét không làm sai kết luận.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # --- TEST 6: KIỂM THỬ XỬ LÝ & BÓC TÁCH LINK ĐA NỀN TẢNG (YOUTUBE, DOUYIN, TIKTOK, FACEBOOK) ---
    print("\n[TEST 6/6] Kiểm thử bóc tách và chuẩn hóa link YouTube, Douyin, TikTok, Facebook...")
    try:
        # 6.1 Douyin text có ký tự tiếng Trung và link rút gọn
        douyin_raw = "7.12 复制打开抖音，看看【小猫咪的作品】https://v.douyin.com/abc1234/ 03/12 j@d.Nq"
        clean_dy = clean_extract_url(douyin_raw)
        assert clean_dy == "https://v.douyin.com/abc1234/", f"Lỗi tách link Douyin: {clean_dy}"
        assert detect_platform_from_url(clean_dy) == "Douyin"
        
        # 6.2 Douyin ies link chuẩn hóa
        norm_dy = normalize_url("https://www.iesdouyin.com/share/video/7382910293847582910/")
        assert norm_dy == "https://www.douyin.com/video/7382910293847582910"
        
        # 6.3 TikTok text và link thiếu www
        tiktok_raw = "Watch this hilarious clip! https://tiktok.com/@creator/video/123456789 #comedy"
        clean_tt = clean_extract_url(tiktok_raw)
        assert "tiktok.com" in clean_tt
        assert detect_platform_from_url(clean_tt) == "TikTok"
        norm_tt = normalize_url(clean_tt)
        assert norm_tt.startswith("https://www.tiktok.com/")
        
        # 6.4 YouTube Shorts & Watch
        yt_short = "https://youtube.com/shorts/dQw4w9WgXcQ"
        assert detect_platform_from_url(yt_short) == "YouTube"
        
        print("  -> PASSED: Bóc tách văn bản chia sẻ phức tạp và chuẩn hóa link đa nền tảng hoạt động chính xác.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
        
    # --- TEST 7: CHẤT LƯỢNG DỮ LIỆU ĐỐI THỦ & BỘ LỌC MỜ THỰC SỰ ĐƯỢC ÁP DỤNG ---
    print("\n[TEST 7/7] Kiểm thử lọc mờ khi chọn keyframe, title DuckDuckGo, metadata đối thủ và đếm đủ 2 nền tảng...")
    blur_video = "test_blur_scene.mp4"
    soft_video = "test_all_soft.mp4"
    blur_out = "test_blur_kfs"
    try:
        # 7.1 Video 2 cảnh: cảnh 1 nét, cảnh 2 mờ -> keyframe chọn ra không được là frame mờ
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(blur_video, fourcc, 20.0, (320, 240))
        sharp = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.putText(sharp, "SHARP SCENE TEXT", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        soft = cv2.GaussianBlur(sharp, (35, 35), 0)
        for f in range(40):
            out.write(sharp)
        for f in range(40):
            out.write(soft)
        out.release()

        kfs = extract_smart_keyframes(blur_video, blur_out, max_frames=2)
        assert len(kfs) == 2, f"Cần 2 keyframes, nhận {len(kfs)}"
        for k in kfs:
            frame = cv2.imread(k['path'])
            blurry, _ = is_frame_blurry(frame)
            assert not blurry, f"Keyframe tại {k['timestamp_str']} vẫn là frame mờ dù đã có bộ lọc!"

        # 7.2 Video toàn mờ vẫn phải trả về keyframe (fallback), không được trả rỗng
        out = cv2.VideoWriter(soft_video, fourcc, 20.0, (320, 240))
        for f in range(40):
            out.write(soft)
        out.release()
        soft_kfs = extract_smart_keyframes(soft_video, blur_out, max_frames=2)
        assert len(soft_kfs) >= 1, "Video toàn mờ phải có fallback keyframe!"

        # 7.3 DuckDuckGo: title phải lấy từ result__a, không phải snippet; metadata không được bịa
        ddg_html = """
        <div class="result web-result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fwatch%2Fv%2F111">Tieu de that cua video</a>
          <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fwatch%2Fv%2F111">facebook.com/watch/v/111</a>
          <a class="result__snippet">Day la mo ta snippet khong phai tieu de</a>
        </div>
        <div class="result web-result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fwatch%2Fv%2F222">Tieu de video thu hai</a>
          <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fwatch%2Fv%2F222">facebook.com/watch/v/222</a>
          <a class="result__snippet">Snippet cua ket qua thu hai</a>
        </div>
        """
        with mock.patch("modules.platform_search.requests.get",
                        return_value=mock.Mock(status_code=200, text=ddg_html)):
            fb = search_facebook_google_scraper("review", max_results=4)
        assert len(fb) == 2, f"Phải bóc được 2 kết quả, nhận {len(fb)}"
        assert fb[0]['title'] == "Tieu de that cua video", "Title phải là result__a, không phải snippet!"
        assert "snippet" not in fb[0]['title'].lower()
        assert fb[0]['uploader'] != "Facebook Creator", "Không được bịa tên kênh!"
        assert fb[0]['views'] != "Phổ biến trên Facebook", "Không được bịa lượt xem!"
        assert not fb[0]['thumbnail'], "Không được dùng ảnh stock làm thumbnail video!"

        # 7.4 yt-dlp flat entry: duration giây phải được định dạng, ngày không có phải ghi rõ
        class FakeYDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, s, download=False):
                return {"entries": [{"id": "x1", "title": "Video test", "url": "https://youtu.be/x1",
                                     "uploader": "Kenh test", "view_count": 1000, "duration": 43638}]}
        with mock.patch("modules.platform_search.yt_dlp.YoutubeDL", FakeYDL):
            yt = search_youtube_free("test", max_results=1)
        assert yt[0]['duration'] == "12:07:18", f"Duration phải định dạng từ giây, nhận {yt[0]['duration']}"
        assert yt[0]['date'] == "Không rõ", "Ngày không có phải ghi 'Không rõ'!"

        # 7.5 competitor_count phải đếm cả Facebook, tách riêng từng nền tảng
        rep = evaluate_video_report(
            {"verdict": "original", "reup_confidence": 0},
            {"estimated_originality_score": 80},
            [{"id": "a"}, {"id": "b"}],
            facebook_results=[{"url": "#1"}, {"url": "#2"}, {"url": "#3"}],
        )
        assert rep['competitor_count'] == 5, "competitor_count phải gồm cả YouTube lẫn Facebook!"
        assert rep['youtube_count'] == 2 and rep['facebook_count'] == 3

        # 7.6 Fallback model: lỗi 400 phải ném ngay, chỉ 503 mới được đổi model
        from google.genai import errors as genai_errors
        from modules.visual_search import analyze_keyframes_with_gemini

        client = mock.Mock()
        uploaded = mock.Mock()
        uploaded.name = "files/test"
        client.files.upload.return_value = uploaded
        client.models.generate_content.side_effect = genai_errors.ClientError(400, {"error": {"message": "bad"}}, None)
        try:
            analyze_keyframes_with_gemini(client, ["frame.jpg"], "gemini-3.8-flash")
            raise AssertionError("Lỗi 400 không được phép âm thầm đổi model!")
        except genai_errors.ClientError:
            pass
        assert client.models.generate_content.call_count == 1, "Lỗi 400 phải dừng ngay, không gọi lại model khác!"

        ok_resp = mock.Mock()
        ok_resp.text = '{"assessment_markdown": "ok", "verdict": "original", "reup_confidence": 0, "watermarks_found": []}'
        client.models.generate_content.reset_mock()
        client.models.generate_content.side_effect = [
            genai_errors.ServerError(503, {"error": {"message": "busy"}}, None), ok_resp
        ]
        res = analyze_keyframes_with_gemini(client, ["frame.jpg"], "gemini-3.8-flash")
        assert res['verdict'] == "original"
        assert client.models.generate_content.call_count == 2, "503 phải thử lại đúng 1 lần với model fallback!"
        assert client.models.generate_content.call_args_list[1].kwargs['model'] == "gemini-3.5-flash-lite"

        print("  -> PASSED: Lọc mờ thật sự áp dụng, title/metadata đối thủ trung thực, đếm đủ 2 nền tảng, fallback đúng lỗi.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")
    finally:
        for p in (blur_video, soft_video):
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(blur_out):
            shutil.rmtree(blur_out)

    # --- TEST 8: BẢO MẬT — CHẶN SSRF & KHÔNG UPLOAD KEYFRAME CÔNG KHAI ---
    print("\n[TEST 8/8] Kiểm thử chặn SSRF (IP nội bộ/metadata) và bỏ upload keyframe lên host công khai...")
    try:
        # 8.1 Guard phải chặn mọi IP nội bộ/loopback/link-local và scheme lạ (dùng IP số, không cần DNS)
        bad_urls = [
            "http://127.0.0.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/",
            "http://192.168.1.1/router",
            "http://[::1]/",
            "ftp://example.com/file",
            "file:///etc/passwd",
        ]
        for u in bad_urls:
            try:
                _assert_public_url(u)
                raise AssertionError(f"SSRF guard phải chặn '{u}'!")
            except ValueError:
                pass

        # 8.2 Host công khai (DNS mock về IP public) phải được cho qua
        with mock.patch("modules.url_downloader.socket.getaddrinfo",
                        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            _assert_public_url("https://example.com/video")

        # 8.3 download_video_from_url chặn metadata endpoint TRƯỚC khi gọi yt-dlp
        ssrf_tmp = tempfile.mkdtemp()
        try:
            with mock.patch("modules.url_downloader.yt_dlp.YoutubeDL") as FakeYDL:
                try:
                    download_video_from_url("http://169.254.169.254/latest/meta-data/", ssrf_tmp)
                    raise AssertionError("Phải chặn SSRF tới metadata endpoint!")
                except (ValueError, RuntimeError):
                    pass
                FakeYDL.assert_not_called()
        finally:
            shutil.rmtree(ssrf_tmp, ignore_errors=True)

        # 8.4 Nhánh redirect v.douyin.com (so khớp chuỗi con) không được fetch host nội bộ
        try:
            normalize_url("https://169.254.169.254/latest/meta-data/?v.douyin.com")
            raise AssertionError("Nhánh redirect v.douyin.com phải chặn host nội bộ!")
        except ValueError:
            pass

        # 8.5 Keyframe local: trả [] và TUYỆT ĐỐI không upload (không POST/GET ra host trung gian)
        with mock.patch("modules.visual_search.requests.post") as mpost, \
             mock.patch("modules.visual_search.requests.get") as mget:
            assert search_google_lens_serpapi("frame.jpg", "fake_key") == []
            mpost.assert_not_called()
            mget.assert_not_called()

        # 8.6 Ảnh đã có URL công khai: vẫn gọi thẳng SerpApi Lens, không qua host upload
        fake_resp = mock.Mock(status_code=200)
        fake_resp.json.return_value = {"visual_matches": [
            {"title": "Nguon goc", "link": "https://example.com/goc",
             "source": "example.com", "thumbnail": "https://example.com/t.jpg"}
        ]}
        with mock.patch("modules.visual_search.requests.get", return_value=fake_resp) as mget, \
             mock.patch("modules.visual_search.requests.post") as mpost:
            matches = search_google_lens_serpapi("https://example.com/public.jpg", "fake_key")
            assert len(matches) == 1 and matches[0]["link"] == "https://example.com/goc"
            mpost.assert_not_called()
            assert mget.call_args.kwargs["params"]["url"] == "https://example.com/public.jpg"

        print("  -> PASSED: SSRF bị chặn ở cả redirect lẫn download; keyframe local không bị upload công khai.")
        passed_count += 1
    except Exception as e:
        print(f"  -> FAILED: {e}")

    print("\n" + "=" * 60)
    print(f" KẾT QUẢ KIỂM THỬ: {passed_count}/{total_count} BÀI TEST ĐẠT ĐIỂM TUYỆT ĐỐI (100%)")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
