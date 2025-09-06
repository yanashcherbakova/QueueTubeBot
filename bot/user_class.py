from bot.db_connection import run_query,simple_insert, get_or_create_default_playlist

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