"""
Module: content_analyzer.py
Tầng 2: Phân tích Kịch bản & Ý tưởng (Content & Semantic Analysis)
- Đưa video (hoặc Audio + Keyframes) vào Gemini Flash để "xem" và hiểu tường tận nội dung
- Trích xuất: Hook mở đầu, Tóm tắt kịch bản, Thông điệp chính
- Tự động tạo bộ từ khóa tìm kiếm (Search Queries) chuyên sâu cho YouTube và Facebook
"""

import os
import json
import logging
import shutil
import subprocess
from google import genai
from google.genai import types

from modules import is_retryable_api_error

logger = logging.getLogger(__name__)


def ensure_ascii_filepath(filepath: str) -> tuple[str, bool]:
    """
    Đảm bảo đường dẫn file chỉ chứa ký tự ASCII ở phần tên file,
    tránh lỗi 'ascii codec can't encode' khi các SDK HTTP (httpx/urllib3) gán Header.
    """
    filename = os.path.basename(filepath)
    try:
        filename.encode('ascii')
        return filepath, False
    except UnicodeEncodeError:
        ext = os.path.splitext(filepath)[1] or ".mp4"
        dir_name = os.path.dirname(filepath)
        safe_copy = os.path.join(dir_name, f"safe_media_upload{ext}")
        shutil.copy2(filepath, safe_copy)
        return safe_copy, True


def extract_audio_if_large(video_path: str, max_size_mb: int = 40) -> str:
    """
    Nếu video lớn hơn max_size_mb, trích xuất audio MP3 để gửi lên Gemini nhanh hơn rất nhiều.
    Đảm bảo tên file audio là ASCII thuần túy.
    """
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb <= max_size_mb:
        return video_path
        
    audio_path = os.path.join(os.path.dirname(video_path), "extracted_audio.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "4",
        audio_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(audio_path):
            return audio_path
    except Exception:
        pass
        
    return video_path


def analyze_video_content(client: genai.Client, video_path: str, keyframe_paths: list[str] = None, model: str = "gemini-3.8-flash") -> dict:
    """
    Gửi video lên Gemini để phân tích nội dung, kịch bản và sinh từ khóa đối thủ.
    Trả về dict chứa thông tin chi tiết có cấu trúc.
    """
    target_media = extract_audio_if_large(video_path)
    is_audio_only = target_media.endswith(".mp3")
    
    # Đảm bảo đường dẫn upload là ASCII an toàn
    safe_target_path, is_copied = ensure_ascii_filepath(target_media)
    
    uploaded_files = []
    try:
        # Upload video hoặc audio
        media_file = client.files.upload(file=safe_target_path)
        uploaded_files.append(media_file)
        
        # Nếu chỉ có audio, upload thêm 3-4 keyframe ảnh để Gemini vừa nghe vừa thấy hình
        if is_audio_only and keyframe_paths:
            for kf in keyframe_paths[:4]:
                uf = client.files.upload(file=kf)
                uploaded_files.append(uf)
                
        prompt = """
        Bạn là chuyên gia phân tích chiến lược nội dung video (Content Strategist) trên YouTube, Facebook và TikTok.
        Hãy phân tích file video/audio được cung cấp và trả về kết quả dưới dạng JSON hợp lệ (không kèm markdown ngoài ```json ... ```) với cấu trúc sau:

        {
            "title_suggestion": "Tiêu đề video tóm tắt ngắn gọn",
            "topic_category": "Chủ đề (ví dụ: Công nghệ / DIY, Ẩm thực, Review phim, Hài hước...)",
            "hook_analysis": "Phân tích câu mở đầu / hình ảnh giữ chân người xem trong 3 giây đầu (Hook)",
            "summary": "Tóm tắt nội dung video trong 3-4 câu",
            "script_breakdown": [
                {"timestamp": "00:00", "content": "Mở đầu..."},
                {"timestamp": "00:15", "content": "Nội dung chính..."}
            ],
            "core_idea": "Ý tưởng / góc tiếp cận cốt lõi của video này là gì?",
            "youtube_queries": [
                "Từ khóa tìm kiếm YouTube 1 (Tiếng Việt, sát kịch bản)",
                "Từ khóa tìm kiếm YouTube 2 (Dạng review/so sánh)",
                "Search query in English (cho nội dung quốc tế)"
            ],
            "facebook_queries": [
                "Từ khóa tìm kiếm Facebook Reels / Watch 1",
                "Từ khóa tìm kiếm Facebook 2"
            ],
            "originality_assessment": "Nhận định: Ý tưởng này đã phổ biến hay có điểm gì mới lạ? Những ai đã từng làm mô-típ tương tự?",
            "estimated_originality_score": 75
        }
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
        
        raw_text = response.text or "{}"
        
        # Parse JSON từ response của Gemini
        clean_json = raw_text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
        try:
            data = json.loads(clean_json)
            return data
        except Exception:
            # Fallback nếu JSON bị lỗi format
            return {
                "title_suggestion": "Video Analysis",
                "topic_category": "Chung",
                "hook_analysis": "Không xác định",
                "summary": raw_text,
                "script_breakdown": [],
                "core_idea": raw_text[:200],
                "youtube_queries": [raw_text[:50]],
                "facebook_queries": [raw_text[:50]],
                "originality_assessment": "Xem tóm tắt chi tiết.",
                "estimated_originality_score": 50
            }
            
    finally:
        # Dọn dẹp media đã upload lên Gemini
        for uf in uploaded_files:
            try:
                client.files.delete(name=uf.name)
            except Exception:
                pass
        # Nếu đã tạo file audio tạm thì xóa đi
        if is_audio_only and os.path.exists(target_media) and target_media != video_path:
            try:
                os.remove(target_media)
            except Exception:
                pass
        # Nếu đã tạo bản sao tên ASCII an toàn thì xóa đi
        if is_copied and os.path.exists(safe_target_path) and safe_target_path != video_path:
            try:
                os.remove(safe_target_path)
            except Exception:
                pass
