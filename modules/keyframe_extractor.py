"""
Module: keyframe_extractor.py
Trích xuất các khung hình (keyframes) thông minh từ video:
- Phát hiện chuyển cảnh (Scene Change Detection)
- Lọc bỏ khung hình quá tối, quá sáng hoặc bị mờ (Laplacian blur filter)
- Chọn ra các khung hình đại diện tiêu biểu nhất
"""

import os
import subprocess
import cv2
import numpy as np


def trim_video_fast(video_path: str, output_path: str, max_duration_sec: int = 15) -> str:
    """
    Cắt nhanh N giây đầu tiên của video (thường là 10s hoặc 15s) bằng FFmpeg.
    Chỉ mất khoảng 0.2 - 0.5 giây và giảm dung lượng file xuống dưới 2-3MB.
    """
    if not max_duration_sec:
        return video_path
        
    cmd = [
        "ffmpeg", "-y", "-ss", "0", "-t", str(max_duration_sec),
        "-i", video_path, "-c", "copy", output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
    except Exception:
        # Nếu cắt trực tiếp (copy stream) gặp lỗi keyframe, re-encode cực nhanh ultrafast
        cmd_reencode = [
            "ffmpeg", "-y", "-ss", "0", "-t", str(max_duration_sec),
            "-i", video_path, "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", output_path
        ]
        try:
            subprocess.run(cmd_reencode, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                return output_path
        except Exception:
            pass
            
    return video_path


def is_frame_blurry(frame, threshold=60.0):
    """Kiểm tra frame có bị mờ (motion blur / out of focus) không bằng Laplacian variance."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance < threshold, variance


def is_frame_extreme_brightness(frame, min_bright=8, max_bright=248):
    """Kiểm tra frame có quá tối (gần như đen xì) hoặc quá chói (trắng xóa) không."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_val = np.mean(gray)
    return (mean_val < min_bright or mean_val > max_bright), mean_val


def extract_smart_keyframes(video_path: str, output_dir: str, max_frames: int = 5) -> list[dict]:
    """
    Trích xuất các keyframe chất lượng cao nhất từ video.
    Trả về danh sách dict: [{'path': ..., 'timestamp_sec': ..., 'score': ...}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise ValueError(f"Không thể mở file video: {video_path}")
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if total_frames > 0 else 0
    
    # Bước nhảy mẫu (sample interval): lấy khoảng 40-60 ứng viên rải đều video
    sample_count = min(60, max(20, total_frames // 10))
    sample_indices = np.linspace(int(fps * 0.5), max(int(fps * 0.5) + 1, total_frames - int(fps * 0.5)), sample_count, dtype=int)
    
    candidates = []
    prev_gray = None
    
    for idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        success, frame = cap.read()
        if not success or frame is None:
            continue
            
        timestamp_sec = idx / fps
        is_extreme, mean_bright = is_frame_extreme_brightness(frame)
        if is_extreme:
            continue
            
        is_blur, blur_score = is_frame_blurry(frame)
        
        # Tính độ khác biệt so với frame trước đó (Scene transition score)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff_score = 0.0
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            diff_score = np.mean(diff)
        prev_gray = gray
        
        # Tổng hợp điểm chất lượng
        overall_score = blur_score * 0.6 + diff_score * 4.0
        
        candidates.append({
            'frame': frame,
            'index': idx,
            'timestamp_sec': timestamp_sec,
            'blur_score': blur_score,
            'blurry': is_blur,
            'diff_score': diff_score,
            'score': overall_score
        })
        
    cap.release()

    # Chỉ giữ frame nét; nếu cả video đều mờ thì giữ lại tất cả để còn có fallback.
    sharp_candidates = [c for c in candidates if not c['blurry']]
    if sharp_candidates:
        candidates = sharp_candidates
    
    if not candidates:
        # Fallback khẩn cấp nếu video quá ngắn hoặc đặc biệt
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        success, frame = cap.read()
        cap.release()
        if success and frame is not None:
            fallback_path = os.path.join(output_dir, "keyframe_01.jpg")
            cv2.imwrite(fallback_path, frame)
            return [{
                'path': fallback_path,
                'filename': "keyframe_01.jpg",
                'timestamp_sec': 0.0,
                'timestamp_str': "00:00",
                'score': 100.0
            }]
        return []
        
    # Chọn ra max_frames khung hình có phân bố thời gian hợp lý và điểm cao nhất
    # Chia video thành các khoảng thời gian (clusters) để tránh chọn 5 frame sát sạt nhau
    time_window = duration_sec / max_frames if duration_sec > 0 else 1.0
    selected_candidates = []
    # So sánh theo index, không so sánh dict: dict chứa numpy array sẽ ném ValueError.
    selected_indices = set()

    for i in range(max_frames):
        window_start = i * time_window
        window_end = (i + 1) * time_window
        window_candidates = [
            c for c in candidates
            if window_start <= c['timestamp_sec'] <= window_end and c['index'] not in selected_indices
        ]

        if window_candidates:
            # Chọn frame có điểm chất lượng cao nhất trong window này
            best = max(window_candidates, key=lambda c: c['score'])
        else:
            # Nếu window không có, lấy frame gần nhất chưa được chọn
            remaining = [c for c in candidates if c['index'] not in selected_indices]
            if not remaining:
                break
            best = min(remaining, key=lambda c: abs(c['timestamp_sec'] - (window_start + window_end) / 2))

        selected_candidates.append(best)
        selected_indices.add(best['index'])
                
    # Lưu các frame đã chọn ra đĩa
    saved_keyframes = []
    for rank, item in enumerate(selected_candidates, start=1):
        ts = item['timestamp_sec']
        minutes = int(ts // 60)
        seconds = int(ts % 60)
        filename = f"keyframe_{rank:02d}_{minutes:02d}m{seconds:02d}s.jpg"
        save_path = os.path.join(output_dir, filename)
        cv2.imwrite(save_path, item['frame'])
        
        saved_keyframes.append({
            'path': save_path,
            'filename': filename,
            'timestamp_sec': round(ts, 2),
            'timestamp_str': f"{minutes:02d}:{seconds:02d}",
            'score': round(item['score'], 2)
        })
        
    return saved_keyframes
