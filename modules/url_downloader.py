"""
Module: url_downloader.py
Tự động nhận diện, trích xuất, chuẩn hóa và tải video từ đa nền tảng:
- Douyin (TikTok Trung Quốc): Tự động lọc văn bản chia sẻ tiếng Trung, xử lý link v.douyin.com, iesdouyin
- TikTok: Xử lý link vt.tiktok.com, vm.tiktok.com, m.tiktok.com, link web
- YouTube: Video chuẩn, Shorts, link rút gọn youtu.be
- Facebook: Facebook Watch, Reels, video công khai, link fb.watch
- Hỗ trợ hầu hết các nền tảng video phổ biến qua yt-dlp
"""

import os
import re
import hashlib
import ipaddress
import socket
import urllib.request
import urllib.parse
import yt_dlp


def _assert_public_url(url: str) -> None:
    """
    Chặn SSRF: chỉ cho phép http(s) tới host CÔNG KHAI.
    Từ chối IP nội bộ/riêng tư, loopback, link-local (metadata cloud 169.254.x),
    reserved, multicast và unspecified. Ném ValueError nếu vi phạm.
    Lưu ý: guard phân giải DNS rồi kiểm tra; không pin IP nên chưa chống được
    DNS-rebinding (TOCTOU) — chấp nhận được với tool chạy LAN nội bộ.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Chỉ hỗ trợ link http/https, không hỗ trợ '{parsed.scheme or url}'.")
    host = parsed.hostname
    if not host:
        raise ValueError(f"Link không có tên miền hợp lệ: '{url}'")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Không phân giải được tên miền '{host}'.")
    for info in infos:
        addr = info[4][0].split('%')[0]  # bỏ scope_id của IPv6 link-local
        ip = ipaddress.ip_address(addr)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"Từ chối truy cập địa chỉ nội bộ/riêng tư ('{host}' -> {ip}).")


def clean_extract_url(text: str) -> str:
    """
    Tự động tách link URL sạch từ văn bản chia sẻ phức tạp
    (Ví dụ khi copy từ app Douyin/TikTok thường kèm theo text tiếng Trung, emoji và hashtag).
    """
    if not text:
        return ""
    text = text.strip()
    match = re.search(r'https?://[^\s<>"]+', text)
    if match:
        url = match.group(0)
        # Làm sạch các ký tự dính ở cuối link (dấu ngoặc, chấm, phẩy tiếng Trung, v.v.)
        url = re.sub(r'[)\]}>,;。，、？！…]+$', '', url)
        return url
    return text


def normalize_url(url: str) -> str:
    """
    Chuẩn hóa URL từ các nền tảng (YouTube, Douyin, TikTok, Facebook)
    để yt-dlp và các extractor nhận diện chính xác 100%.
    """
    if not url:
        return ""
    url = url.strip()

    # 1. Douyin handling (TikTok Trung Quốc)
    if "douyin.com" in url or "iesdouyin.com" in url:
        # Nếu là iesdouyin share link hoặc có /video/ID
        m = re.search(r'/(?:video|share/video)/(\d+)', url)
        if m:
            return f"https://www.douyin.com/video/{m.group(1)}"
            
        # Nếu là v.douyin.com link rút gọn từ app
        if "v.douyin.com" in url:
            _assert_public_url(url)
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
                    }
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    final_url = resp.geturl()
                    m2 = re.search(r'/(?:video|share/video)/(\d+)', final_url)
                    if m2:
                        return f"https://www.douyin.com/video/{m2.group(1)}"
                    return final_url
            except Exception:
                pass
                
        # Đảm bảo có www.douyin.com
        if re.search(r'^https?://douyin\.com', url):
            url = re.sub(r'^https?://douyin\.com', 'https://www.douyin.com', url)
        return url

    # 2. TikTok handling
    if "tiktok.com" in url:
        # Xử lý m.tiktok.com/v/123456 -> www.tiktok.com/@tiktok/video/123456
        m = re.search(r'm\.tiktok\.com/v/(\d+)', url)
        if m:
            return f"https://www.tiktok.com/@tiktok/video/{m.group(1)}"
            
        # Đảm bảo www.tiktok.com nếu người dùng paste https://tiktok.com/... (yt-dlp yêu cầu www)
        if re.search(r'^https?://tiktok\.com', url):
            url = re.sub(r'^https?://tiktok\.com', 'https://www.tiktok.com', url)
        return url

    # 3. Facebook handling
    if "fb.watch" in url:
        _assert_public_url(url)
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.geturl()
        except Exception:
            return url

    # 4. YouTube handling: Tách bớt list/radio không cần thiết để tránh tải nhầm playlist
    if "youtube.com/watch" in url and "&list=" in url:
        url = re.sub(r'&list=[^&]+', '', url)

    return url


def detect_platform_from_url(url: str) -> str:
    """Nhận diện nền tảng dựa trên URL."""
    lower_url = url.lower()
    if "douyin.com" in lower_url or "iesdouyin.com" in lower_url:
        return "Douyin"
    elif "tiktok.com" in lower_url:
        return "TikTok"
    elif "youtube.com" in lower_url or "youtu.be" in lower_url:
        return "YouTube"
    elif "facebook.com" in lower_url or "fb.watch" in lower_url:
        return "Facebook"
    elif "instagram.com" in lower_url:
        return "Instagram"
    elif "kuaishou.com" in lower_url:
        return "Kuaishou"
    return "Web Video"


def download_video_from_url(raw_input: str, output_dir: str) -> dict:
    """
    Tải video về thư mục tạm với cấu hình tối ưu, chống chặn và tương thích đa nền tảng.
    Trả về dict chứa đường dẫn file video, tiêu đề, thời lượng và thumbnail.
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_url = clean_extract_url(raw_input)
    if not clean_url or not clean_url.startswith("http"):
        raise ValueError(f"Đường link không hợp lệ: '{raw_input}'")
        
    normalized_url = normalize_url(clean_url)
    _assert_public_url(normalized_url)
    platform_name = detect_platform_from_url(normalized_url)
    
    # Tạo tên file duy nhất theo hash của link để tránh trùng lặp hoặc xung đột cache
    url_hash = hashlib.md5(normalized_url.encode('utf-8')).hexdigest()[:10]
    out_template = os.path.join(output_dir, f"video_{url_hash}.%(ext)s")
    
    # Cấu hình yt-dlp tối ưu cho video ngắn và đa nền tảng
    ydl_opts = {
        'outtmpl': out_template,
        # Ưu tiên trực tiếp mp4 mux sẵn để tải nhanh nhất; nếu không có thì mux 1080p
        'format': 'best[height<=1080]/bestvideo[height<=1080]+bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'overwrites': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,vi;q=0.8,en-US;q=0.7,en;q=0.6',
        }
    }
    
    # Tinh chỉnh riêng cho Douyin để tránh chặn bot
    if platform_name == "Douyin":
        ydl_opts['http_headers']['Referer'] = 'https://www.douyin.com/'
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalized_url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Nếu file sinh ra có đuôi khác (webm/mkv), tìm file thực tế
            if not os.path.exists(filename):
                base_name = os.path.splitext(filename)[0]
                for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                    candidate = base_name + ext
                    if os.path.exists(candidate):
                        filename = candidate
                        break
                        
            return {
                "video_path": filename,
                "title": info.get("title", "Video"),
                "uploader": info.get("uploader") or info.get("channel") or platform_name,
                "duration": info.get("duration") or 0,
                "thumbnail": info.get("thumbnail"),
                "platform": platform_name,
                "original_url": clean_url,
                "normalized_url": normalized_url
            }
    except Exception as e:
        err_msg = str(e)
        if "Private video" in err_msg:
            raise RuntimeError(f"Video này đang ở chế độ Riêng tư (Private) trên {platform_name}, không thể quét.")
        elif "Video unavailable" in err_msg or "deleted" in err_msg.lower():
            raise RuntimeError(f"Video không tồn tại hoặc đã bị xóa trên {platform_name}.")
        else:
            raise RuntimeError(f"Lỗi khi tải video từ {platform_name}: {err_msg}")
