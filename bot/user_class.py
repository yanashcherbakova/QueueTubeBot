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
    

    @classmethod
    def validate_or_reload(cls, context, update):
        Cur_user = context.user_data.get("user")
        if Cur_user:
            return Cur_user

        u = update.effective_user
        Cur_user = cls(u.id, u.username)

        res = run_query("SELECT id FROM users WHERE telegram_id = %s", (u.id,), fetchone=True)
        if res:
            Cur_user.user_id = res[0] if isinstance(res, (tuple, list)) else res
        else:
            Cur_user.save_to_db()

        Cur_user.get_or_create_default_playlist()
        context.user_data["user"] = Cur_user
        return Cur_user

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
    

    def get_user_stat(self):
        playlists_count = run_query("""
            SELECT count(p.id)
                         FROM playlists p
                         WHERE p.user_id = %s;""", (self.user_id,), fetchone = True)
        
        row = run_query("""
            SELECT
                COALESCE(SUM(CASE WHEN pit.status = 'done'  THEN 1 END), 0) AS done_cnt,
                COALESCE(SUM(CASE WHEN pit.status = 'done'  THEN pit.duration_sec END), 0) AS done_sec,
                COALESCE(SUM(CASE WHEN pit.status = 'await' THEN 1 END), 0) AS await_cnt,
                COALESCE(SUM(CASE WHEN pit.status = 'await' THEN pit.duration_sec END), 0) AS await_sec
            FROM playlists p
            JOIN playlist_items pit ON pit.playlist_id = p.id
            WHERE p.user_id = %s;
        """, (self.user_id,), fetchone=True)

        done_cnt, done_sec, await_cnt, await_sec = row if row else (0, 0, 0, 0)

        def fmt_hm(total_sec: int) -> str:
            mins = total_sec // 60
            hrs = mins // 60
            return f"{hrs} h {mins - hrs * 60} min"

        done_str = fmt_hm(done_sec)
        await_str = fmt_hm(await_sec)

        total_sec = done_sec + await_sec
        done_percentage = (done_sec * 100) // total_sec if total_sec > 0 else 0

        if done_percentage == 100:
            pic = '⬛⬛⬛⬛⬛⬛'
        elif done_percentage >= 80:
            pic = '⬛⬛⬛⬛⬛⬜'
        elif done_percentage >= 60:
            pic = '⬛⬛⬛⬛⬜⬜'
        elif done_percentage >= 40:
            pic = '⬛⬛⬛⬜⬜⬜'
        elif done_percentage >= 20:
            pic = '⬛⬛⬜⬜⬜⬜'
        else:
            pic = '⬛⬜⬜⬜⬜⬜'

        stat = ['User statistic:','\n', '\n',  
                f"Playlist count: {playlists_count[0] - 1}", '\n', 
                f"Videos done: {done_cnt}", '\n',
                f"Videos await: {await_cnt}",'\n', '\n', 
                f"⏳ Time await {await_str}",'\n',
                f"⌛ Time watched: {done_str}", '\n', '\n', 
                f"Progress: {pic}({done_percentage}%)"]
        return "".join(stat)