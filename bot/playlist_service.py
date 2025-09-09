from bot.yt_parse import detect_youtube_type, parse_playlist, parse_single_video
from bot.db_connection import run_query,simple_insert


class PlaylistService:
    @staticmethod
    def add_playlist(user_id, link):
        playlist_info, items = parse_playlist(link)

        columns = ['user_id', 'youtube_link', 'title', 'full_duration']

        playlist_id = run_query(
            simple_insert('playlists', 4, columns, 1, 1, ['user_id', 'youtube_link'], 'id'),
            (user_id, playlist_info["playlist_link"], playlist_info["playlist_title"], playlist_info["full_duration"]),
            fetchone=True)

        if not playlist_id:
            return None

        for i in items:
            run_query(
                simple_insert(
                    'playlist_items', 5,
                    ['playlist_id', 'position_num', 'title', 'link', 'duration_sec']),
                    (playlist_id, i["position_num"], i["title"], i["link"], i["duration_sec"]))
        return playlist_id

    @staticmethod
    def add_video(playlist_id, link):
        db_data = parse_single_video(link)
        dur = db_data.get("duration_sec") or 0

        row = run_query("""
            SELECT COALESCE(MAX(position_num), 0) + 1
            FROM playlist_items
            WHERE playlist_id = %s;
            """,
            (playlist_id,), fetchone=True)
        next_pos = row[0] if row else 1

        columns = ['playlist_id', 'position_num', 'title', 'link', 'duration_sec']

        run_query(
            simple_insert('playlist_items', 5, columns),
            (playlist_id, next_pos, db_data["title"], db_data["link"], dur))
        
        run_query("""
            UPDATE playlists p
                                    SET full_duration = COALESCE(full_duration, 0) + %s
                                    WHERE p.id = %s;
            """, (dur, playlist_id))
        
        return db_data["title"]
    
    @staticmethod
    def set_playlist_await(playlist_id, user_id):
        res = run_query("""
            UPDATE playlists p
            SET status = 'await',
                completed_at = NULL
            WHERE p.id = %s
                AND p.user_id = %s
                AND EXISTS (
                    SELECT 1
                    FROM playlist_items pit
                    WHERE pit.playlist_id = p.id
                    AND pit.status = 'await'
                    )
            RETURNING p.id;
            """, (playlist_id, user_id), fetchone=True)
        return 1 if res else 0