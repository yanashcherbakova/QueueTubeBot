import yt_dlp

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


ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "simulate": True,
    "ignoreerrors": True, 
}

def detect_youtube_type(link):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception:
        return "unknown"
    t = info.get("_type")
    if t == "playlist":
        return "playlist"
    if t in (None, "video"):
        return "video"
    return "unknown"
    

def parse_single_video(link):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
    except Exception:
        return {"title": None, "link": link, "duration_sec": None}
    return {
        "title": info.get("title"),
        "link": info.get("webpage_url") or link,
        "duration_sec": info.get("duration"),
    }


def parse_playlist(link):
    flat_opts = {
        **ydl_opts,
        "extract_flat": "in_playlist",  
        "lazy_playlist": True,
    }
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(link, download=False)

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


    




