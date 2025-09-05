import re 

#1 to check link

YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.)?(youtube\.com|youtu\.be)/\S+$",
    re.IGNORECASE
)

def is_youtube_link(text):
    return bool(text) and bool(YOUTUBE_URL_RE.match(text.strip()))

