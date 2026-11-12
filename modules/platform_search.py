"""
Module: platform_search.py
Tìm kiếm đối thủ cạnh tranh trên YouTube & Facebook:
- Sử dụng yt-dlp để quét trực tiếp YouTube (không cần API Key, hoàn toàn miễn phí)
- Trích xuất tiêu đề, kênh, lượt xem (views), ngày đăng và link video
- Tạo cú pháp tìm kiếm chuyên sâu (Google Dorks) cho Facebook Reels & Facebook Watch
- Hỗ trợ lấy link đối thủ trên Facebook qua tìm kiếm web
"""

import concurrent.futures
import logging
import urllib.parse
import yt_dlp
import requests

logger = logging.getLogger(__name__)


def format_duration(seconds) -> str:
    """yt-dlp flat entry chỉ có duration dạng giây, không có duration_string."""
    if not seconds or seconds < 0:
        return "Không rõ"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def search_youtube_free(query: str, max_results: int = 5) -> list[dict]:
    """
    Tìm kiếm video trên YouTube bằng yt-dlp (Không cần YouTube Data API Key).
    """
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'playlist_items': f'1-{max_results}'
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_str = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_str, download=False)
            
            if 'entries' in info:
                for entry in info['entries']:
                    if not entry:
                        continue
                    video_id = entry.get('id')
                    title = entry.get('title', 'Không có tiêu đề')
                    url = entry.get('url') or f"https://www.youtube.com/watch?v={video_id}"
                    uploader = entry.get('uploader') or entry.get('channel', 'Ẩn danh')
                    view_count = entry.get('view_count')
                    view_str = f"{view_count:,} views" if view_count is not None else "N/A"
                    duration = entry.get('duration_string') or format_duration(entry.get('duration'))
                    upload_date = entry.get('upload_date')
                    if upload_date and len(upload_date) == 8:
                        upload_date = f"{upload_date[6:8]}/{upload_date[4:6]}/{upload_date[0:4]}"
                    else:
                        upload_date = "Không rõ"
                        
                    thumbnail = entry.get('thumbnail')
                    if not thumbnail and video_id:
                        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                        
                    results.append({
                        "id": video_id,
                        "title": title,
                        "url": url,
                        "uploader": uploader,
                        "views": view_str,
                        "duration": duration,
                        "date": upload_date,
                        "thumbnail": thumbnail,
                        "platform": "YouTube"
                    })
    except Exception as e:
        logger.warning("Lỗi khi tìm kiếm YouTube cho query '%s': %s", query, e)
        raise
        
    return results


def search_multiple_queries_youtube(queries: list[str], max_per_query: int = 3) -> dict:
    """
    Tìm kiếm đồng thời nhiều query trên YouTube bằng đa luồng (song song) và loại bỏ trùng lặp.
    Trả về videos + failed_queries + query_count + ok để nơi gọi phân biệt được
    "không có đối thủ" với "không quét được".
    """
    clean_queries = [q.strip() for q in queries if q and q.strip()]
    scan = {"videos": [], "failed_queries": [], "query_count": len(clean_queries), "ok": False}
    if not clean_queries:
        return scan
        
    seen_ids = set()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(clean_queries))) as executor:
        future_to_query = {
            executor.submit(search_youtube_free, q, max_per_query): q
            for q in clean_queries
        }
        for future in concurrent.futures.as_completed(future_to_query):
            query = future_to_query[future]
            try:
                vids = future.result()
            except Exception as e:
                logger.warning("Lỗi truy vấn '%s': %s", query, e)
                scan["failed_queries"].append(query)
                continue
            for v in vids:
                vid_id = v.get('id')
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    scan["videos"].append(v)
                
    scan["ok"] = len(scan["failed_queries"]) < len(clean_queries)
    return scan


def generate_facebook_search_links(queries: list[str]) -> list[dict]:
    """
    Tạo các đường link tìm kiếm chuyên biệt cho Facebook Watch và Reels theo từ khóa.
    """
    fb_targets = []
    for q in queries:
        encoded = urllib.parse.quote(q)
        fb_watch_url = f"https://www.facebook.com/watch/search/?q={encoded}"
        google_fb_dork = f"https://www.google.com/search?q=site%3Afacebook.com%2Fwatch+%22{encoded}%22"
        google_fb_reel_dork = f"https://www.google.com/search?q=site%3Afacebook.com%2Freel+%22{encoded}%22"
        
        fb_targets.append({
            "query": q,
            "watch_url": fb_watch_url,
            "google_dork_watch": google_fb_dork,
            "google_dork_reels": google_fb_reel_dork
        })
    return fb_targets


def clean_duckduckgo_url(raw_href: str) -> str:
    """Giải mã link redirect từ DuckDuckGo để lấy URL trực tiếp của Facebook."""
    if "uddg=" in raw_href:
        try:
            return urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
        except Exception:
            pass
    if raw_href.startswith("//"):
        return "https:" + raw_href
    return raw_href


def search_facebook_google_scraper(query: str, max_results: int = 4) -> list[dict]:
    """
    Tìm kiếm các link video Facebook công khai qua DuckDuckGo HTML (không cần API key).
    """
    dork = f"site:facebook.com/watch {query}"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(dork)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    fb_results = []
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            from lxml import html
            tree = html.fromstring(resp.text)
            # Title thật nằm ở result__a; result__snippet chỉ là mô tả, không phải tiêu đề.
            for block in tree.xpath('//div[contains(@class, "web-result")]')[:max_results]:
                title_a = block.xpath('.//a[@class="result__a"]')
                url_a = block.xpath('.//a[@class="result__url"]')
                if not title_a or not url_a:
                    continue
                clean_url = clean_duckduckgo_url(url_a[0].get('href', '').strip())
                if "facebook.com" not in clean_url:
                    continue
                title_text = title_a[0].text_content().strip()
                fb_results.append({
                    "title": title_text[:90] + "..." if len(title_text) > 90 else title_text,
                    "url": clean_url,
                    # DuckDuckGo không trả về kênh/view/thời lượng/ngày đăng: không được bịa.
                    "uploader": "Không rõ",
                    "views": "Không rõ",
                    "duration": "Không rõ",
                    "date": "Không rõ",
                    "thumbnail": None,
                    "platform": "Facebook"
                })
    except Exception:
        pass
        
    return fb_results


def search_multiple_queries_facebook(queries: list[str], max_per_query: int = 3) -> list[dict]:
    """
    Tìm kiếm video trên Facebook với nhiều từ khóa và loại bỏ trùng lặp.
    """
    clean_queries = [q.strip() for q in queries if q.strip()]
    if not clean_queries:
        return []
        
    all_fb = []
    seen_urls = set()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(clean_queries))) as executor:
        futures = {
            executor.submit(search_facebook_google_scraper, q, max_per_query): q
            for q in clean_queries
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                vids = future.result()
                for v in vids:
                    u = v.get('url')
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        all_fb.append(v)
            except Exception:
                pass
                
    return all_fb
