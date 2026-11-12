"""
Module: visual_search.py
Tầng 1: Phân tích thị giác & Tìm kiếm hình ảnh (Google Lens / Reverse Search)
- Sử dụng Gemini Vision để soi xét từng keyframe (phát hiện watermark, logo kênh, diễn viên, trích đoạn phim, clip Douyin/TikTok)
- Hỗ trợ SerpApi Google Lens (nếu có API Key)
- Tự động sinh link tra cứu trực tiếp Google Lens, Yandex Images, Bing Visual Search
"""

import json
import logging
import os
import shutil
import urllib.parse
import requests
from google import genai
from google.genai import types

from modules import is_retryable_api_error

logger = logging.getLogger(__name__)


def ensure_ascii_filepath(filepath: str) -> tuple[str, bool]:
    filename = os.path.basename(filepath)
    try:
        filename.encode('ascii')
        return filepath, False
    except UnicodeEncodeError:
        ext = os.path.splitext(filepath)[1] or ".jpg"
        safe_copy = os.path.join(os.path.dirname(filepath), f"safe_frame_{os.getpid()}_{hash(filepath) & 0xffff}{ext}")
        shutil.copy2(filepath, safe_copy)
        return safe_copy, True


def analyze_keyframes_with_gemini(client: genai.Client, keyframe_paths: list[str], model: str = "gemini-3.8-flash") -> dict:
    """
    Sử dụng Gemini Vision để kiểm tra độ nguyên bản và dấu vết trích xuất trên các khung hình.
    Trả về dict: assessment_markdown để hiển thị + verdict/reup_confidence/watermarks_found để chấm điểm.
    """
    if not keyframe_paths:
        return {
            "assessment_markdown": "Không có khung hình nào để phân tích.",
            "verdict": "uncertain",
            "reup_confidence": 0,
            "watermarks_found": [],
        }
        
    uploaded_files = []
    temp_copies = []
    try:
        for p in keyframe_paths:
            safe_p, copied = ensure_ascii_filepath(p)
            if copied:
                temp_copies.append(safe_p)
            uf = client.files.upload(file=safe_p)
            uploaded_files.append(uf)
            
        prompt = """
        Bạn là chuyên gia giám định bản quyền video và thẩm định nội dung số.
        Hãy quan sát kỹ các khung hình (keyframes) được trích xuất từ video này.

        Trả về DUY NHẤT một JSON hợp lệ (không markdown, không chữ nào ngoài JSON) với cấu trúc:
        {
            "assessment_markdown": "Phân tích chi tiết dạng markdown gồm 3 mục: (1) Dấu vết đồ họa & Watermark: logo kênh, watermark TikTok ID/Douyin/CapCut/Kuaishou/logo đài truyền hình, ghi rõ chữ hoặc ID nếu đọc được; phụ đề hardcoded theo phong cách dịch/vietsub từ video Trung Quốc, Hàn Quốc, phương Tây. (2) Nguồn gốc hình ảnh: vlog tự quay, trích đoạn phim/gameshow, review sản phẩm, compilation/reaction, hay clip cắt ghép nước ngoài; nhân vật nổi tiếng, phim điện ảnh, anime hoặc sự kiện cụ thể xuất hiện. (3) Kết luận re-up/bản quyền: tỷ lệ phán đoán (ví dụ 80% cắt từ Douyin, 20% tự quay) và từ khóa hình ảnh để tìm video gốc.",
            "verdict": "original | reup | uncertain",
            "reup_confidence": 0,
            "watermarks_found": []
        }

        Quy tắc bắt buộc khi chọn verdict:
        - "original": có bằng chứng cho thấy video tự quay / tự sản xuất.
        - "reup": có bằng chứng CỤ THỂ lấy từ nguồn khác (watermark ID nền tảng, logo đài, phụ đề dịch lại, cảnh phim/anime/gameshow nhận diện được).
        - "uncertain": không đủ bằng chứng để kết luận. Không được đoán bừa.
        reup_confidence là mức tin rằng đây là video re-up, từ 0 đến 100; verdict "original" thì để 0.
        watermarks_found chỉ liệt kê watermark thực sự NHÌN THẤY trong khung hình, không suy đoán; để [] nếu không có.
        """
        
        contents = uploaded_files + [prompt]
        config = types.GenerateContentConfig(response_mime_type="application/json")
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
        except Exception as e:
            if not is_retryable_api_error(e):
                raise
            fallback_model = "gemini-3.5-flash-lite" if model != "gemini-3.5-flash-lite" else "gemini-3.8-flash"
            logger.warning("Model %s lỗi %s, chuyển sang %s: %s", model, e.code, fallback_model, e)
            response = client.models.generate_content(
                model=fallback_model,
                contents=contents,
                config=config
            )

        raw_text = response.text or ""
        try:
            data = json.loads(raw_text)
        except (ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}

        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict not in ("original", "reup", "uncertain"):
            verdict = "uncertain"

        return {
            "assessment_markdown": data.get("assessment_markdown") or raw_text or "Không nhận được phản hồi từ AI.",
            "verdict": verdict,
            "reup_confidence": data.get("reup_confidence", 0),
            "watermarks_found": data.get("watermarks_found") or [],
        }
    finally:
        # Dọn dẹp files đã upload lên Gemini Developer API
        for uf in uploaded_files:
            try:
                client.files.delete(name=uf.name)
            except Exception:
                pass
        for tc in temp_copies:
            try:
                if os.path.exists(tc):
                    os.remove(tc)
            except Exception:
                pass


def search_google_lens_serpapi(image_path: str, serpapi_key: str) -> list[dict]:
    """
    Tìm kiếm bằng Google Lens qua SerpApi (nếu có API key).
    Chỉ nhận ảnh ĐÃ có URL http(s) công khai sẵn. Không tự upload keyframe local lên
    host bên thứ ba (tmpfiles/0x0.st...) để tránh lộ nội dung video riêng tư ra internet.
    Với keyframe local, trả về [] — người dùng dùng link tra cứu ngược thủ công ở giao diện.
    """
    if not serpapi_key:
        return []

    if not image_path or not str(image_path).lower().startswith(("http://", "https://")):
        return []

    try:
        params = {
            "engine": "google_lens",
            "url": image_path,
            "api_key": serpapi_key,
            "hl": "vi"
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            matches = []
            for item in data.get("visual_matches", [])[:8]:
                matches.append({
                    "title": item.get("title", "Không có tiêu đề"),
                    "link": item.get("link", "#"),
                    "source": item.get("source", "Web"),
                    "thumbnail": item.get("thumbnail", "")
                })
            return matches
    except Exception as e:
        logger.warning("Lỗi khi gọi SerpApi Lens: %s", e)

    return []


def generate_reverse_search_urls(query_or_desc: str) -> dict[str, str]:
    """
    Tạo các liên kết tra cứu nhanh đối thủ và hình ảnh trực quan trên Google, YouTube, Facebook.
    """
    encoded = urllib.parse.quote(query_or_desc)
    return {
        "Google Lens": f"https://lens.google.com/",
        "Google Images": f"https://www.google.com/search?tbm=isch&q={encoded}",
        "Yandex Visual": f"https://yandex.com/images/search?text={encoded}",
        "YouTube Search": f"https://www.youtube.com/results?search_query={encoded}",
        "Facebook Watch": f"https://www.facebook.com/watch/search/?q={encoded}",
        "TikTok Search": f"https://www.tiktok.com/search?q={encoded}"
    }
