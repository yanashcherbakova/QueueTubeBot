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
        if not self.user_id:
            raise RuntimeError("get_or_create_default_playlist called without user_id")
        self.default_playlist_id = get_or_create_default_playlist(self.user_id)
        return self.default_playlist_id