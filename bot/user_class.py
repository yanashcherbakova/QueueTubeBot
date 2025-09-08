from bot.db_connection import run_query,simple_insert
import random
from html import escape

class User:
    def __init__(self, tg_id, username, user_id=None):
        self.tg_id = tg_id
        self.username = username
        self.user_id = user_id
        self.default_playlist_id = None

    def save_to_db(self):
        column_name_list = ['telegram_id', 'username']
        row = run_query(
            simple_insert('users', 2, column_name_list, 1, 1, ['telegram_id'], 'id'),
            (self.tg_id, self.username), fetchone=True)
        if row:
            self.user_id = row[0] if isinstance(row, (tuple, list)) else row
        else:
            row = run_query("SELECT id FROM users WHERE telegram_id = %s", (self.tg_id,), fetchone=True)
            if not row:
                raise RuntimeError("User upsert failed: no id returned and not found by telegram_id")
            self.user_id = row[0] if isinstance(row, (tuple, list)) else row
        return self.user_id
    
    def get_or_create_default_playlist(self):
        column_name_list = ['user_id', 'youtube_link', 'title', 'full_duration', 'status']
        playlist_id = run_query(
            simple_insert('playlists', 5, column_name_list, 1, 1, ['user_id', 'youtube_link'], 'id'),
            (self.user_id, "default_playlist", "playlist_for_single_videos", 0, 'await'),
            fetchone=True
            )
        if not playlist_id:
            playlist_id = run_query("""
                SELECT id FROM playlists
                WHERE user_id = %s AND youtube_link = %s
                LIMIT 1;
            """, (self.user_id, "default_playlist"), fetchone=True)

        self.default_playlist_id = playlist_id[0] if playlist_id else None
        return self.default_playlist_id
    

    def get_random_playlist(self):
        tuple_ids = run_query("""
            SELECT p.id
                FROM playlists p
                WHERE p.user_id = %s
          AND EXISTS (
            SELECT 1
            FROM playlist_items pit
            WHERE pit.playlist_id = p.id
            AND COALESCE(TRIM(LOWER(pit.status)), 'await') = 'await'
          )
        ORDER BY random()
        LIMIT 1;
        """, (self.user_id,), fetchall = True)

        if not tuple_ids:
            return None
        playlist_ids = [id[0] for id in tuple_ids]
        random_playlist = random.choice(playlist_ids)
        return random_playlist
    

    def render_playlists(self):
        lists = run_query("""
                WITH ordered AS (
                    SELECT p.id, p.youtube_link, p.title, p.status,
                    COALESCE(SUM(CASE WHEN pit.status = 'done' THEN pit.duration_sec END), 0) AS watched_sec,
                    ROW_NUMBER() OVER (ORDER BY p.id) AS num
                        FROM users u
                        JOIN playlists p ON u.id = p.user_id
                        LEFT JOIN playlist_items pit ON pit.playlist_id = p.id      
                        WHERE u.id = %s and p.youtube_link <> 'default_playlist'
                        GROUP BY p.id, p.youtube_link, p.title, p.status
                    )
                    SELECT id, youtube_link, title, status, watched_sec, num
                          FROM ordered
                          ORDER BY num;""", 
                (self.user_id,), fetchall = True)

        if not lists:
            return "No playlists saved"
    
        lines = ["Your playlists:\n"]
        for pid, link, title, status, watched_sec, num in lists:
            safe_title = escape(title or "(noname)")
            safe_link  = escape(link or "", quote=True)
            safe_status = escape(status or "")
            minutes = int(watched_sec or 0) // 60

            lines.append(
                f"{num} {safe_title}\n"
                f"🔗 <a href=\"{safe_link}\">link</a>\n"
                f"Status: {safe_status}\n"
                f"Watched: {minutes}min\n"
            )
        return "\n".join(lines)