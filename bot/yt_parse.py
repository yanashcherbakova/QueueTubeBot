import yt_dlp
import logging

#playlists table
# -- id
# -- user_id
# -- youtube_link
# -- title
# -- full_duration
# -- status // await -- in_progress -- done
# -- created_at
# -- last_sent
# -- completed_at

#playlist_item
# -- id
# -- playlist_id
# -- position_num
# -- title
# -- link 
# -- duration_sec
# -- status // await -- skipped -- done
# -- completed_at

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class _QuietLogger:
    def debug(self, msg): 
        pass
    def warning(self, msg): 
        pass
    def error(self, msg): 
        pass


def _skip_unavailable(info):
    avail = (info.get("availability") or "").lower()
    title = (info.get("title") or "").lower()

    if avail in {"private", "needs_auth", "subscriber_only", "premium_only"}:
        return "skip: unavailable by availability"

    if title.startswith("[private") or title.startswith("[deleted"):
        return "skip: private/deleted title"
    return None 

BASE_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "simulate": True,
    "ignoreerrors": True, 
    "extractor_retries": 2,  
    "logger": _QuietLogger(),  
    "match_filter": _skip_unavailable,
}

def detect_youtube_type(link):
    opts = {**BASE_YDL_OPTS, "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception as e:
        logger.warning(f"detect error {link}: {e}")
        return "parse_error"
    
    if not info:
        return "parse_error"
    
    t = info.get("_type")
    if t in ("playlist", "multi_video", "compat_list") or ("entries" in info):
        return "playlist"
    if t in (None, "video", "url"): 
        return "video"
    return "unknown"
    

def parse_single_video(link):
    opts = {**BASE_YDL_OPTS, "noplaylist": True, "extract_flat": False}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception as e:
        logger.warning(f"video parse error {link}: {e}")
        return {"title": None, "link": link, "duration_sec": None}
    
    if not info or info.get("_type") == "playlist":
        return {"title": None, "link": link, "duration_sec": None}
    
    return {
        "title": info.get("title"),
        "link": info.get("webpage_url") or link,
        "duration_sec": info.get("duration"),
    }


def parse_playlist(link):
    opts = {**BASE_YDL_OPTS, "extract_flat": "in_playlist", "lazy_playlist": True}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception as e:
        logger.warning(f"playlist parse error {link}: {e}")
        return {"playlist_link": link, "playlist_title": None, "full_duration": 0}, []

    if not info:
        return {"playlist_link": link, "playlist_title": None, "full_duration": 0}, []

    playlist_title = info.get("title")
    entries = info.get("entries") or []

    items = []
    total_sec = 0

    for position, video in enumerate(entries, start=1):
        if not video:
            continue

        avail = (video.get("availability") or "").lower()
        title_l = (video.get("title") or "").lower()
        if avail in {"private", "needs_auth", "subscriber_only", "premium_only"}:
            continue
        if title_l.startswith("[private") or title_l.startswith("[deleted]"):
            continue

        dur = video.get("duration")
        if isinstance(dur, (int, float)):
            total_sec += int(dur)

        video_link = (
            video.get("webpage_url") or
            (f"https://www.youtube.com/watch?v={video.get('id')}" if video.get("id") else None)
        )

        items.append({
            "position_num": position,
            "title": video.get("title"),
            "link": video_link,
            "duration_sec": int(dur) if isinstance(dur, (int, float)) else None,
        })

    playlist_info = {
        "playlist_link": link,
        "playlist_title": playlist_title,
        "full_duration": total_sec,
    }
    return playlist_info, items


    




