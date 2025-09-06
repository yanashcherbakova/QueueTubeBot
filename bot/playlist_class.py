from bot.db_connection import run_query
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Playlist:
    def __init__(self, playlist_id, user_id):
        self.playlist_id = playlist_id
        self.user_id = user_id
        logger.info("Playlist.__init__: playlist_id=%s user_id=%s", self.playlist_id, self.user_id)

    def find_next_video(self):
        info = run_query("""
            SELECT pit.id, pit.link
                FROM playlist_items pit
                JOIN playlists p ON p.id = pit.playlist_id
                    WHERE pit.playlist_id = %s
                    AND p.user_id       = %s
                    AND COALESCE(TRIM(LOWER(pit.status)), 'await') = 'await'
                ORDER BY pit.position_num NULLS FIRST, pit.id
                LIMIT 1;
        """, (self.playlist_id, self.user_id), fetchone = True)
        if not info:
            logger.info("No next video for playlist_id=%s (user_id=%s)", self.playlist_id, self.user_id)
            return None
        
        vid_id, link = info[0], info[1]
        return {"id": vid_id, "link": link}

    def set_playlist_done(self):
        res = run_query("""
            UPDATE playlists p
            SET status = 'done',
                completed_at = NOW()
            WHERE p.id = %s
                AND p.user_id = %s
                AND NOT EXISTS (
                    SELECT 1
                    FROM playlist_items pit
                    WHERE pit.playlist_id = p.id
                    AND pit.status = 'await'
                    )
            RETURNING p.id;
            """, (self.playlist_id, self.user_id), fetchone=True)
        return 1 if res else 0
    
    


    def set_last_sent(self):
        res = run_query("""
            UPDATE playlists p
                    SET last_sent = NOW()
                    WHERE p.id = %s AND p.user_id = %s
                    RETURNING p.id;
        """, (self.playlist_id, self.user_id), fetchone=True)
        return bool(res)

    def delete_playlist(self):
        row = run_query("""
            DELETE FROM playlists p
            WHERE p.id = %s
                AND p.user_id = %s
                AND p.youtube_link <> 'default_playlist'
            RETURNING p.id, p.title, p.youtube_link;
        """, (self.playlist_id, self.user_id), fetchone=True)
        if row:
            deleted = {"id": row[0], "title": row[1], "youtube_link": row[2]}
        
            return deleted
        return None


    def restart(self):
        rows = run_query("""
        UPDATE playlist_items pit
        SET status = 'await', completed_at = NULL
        FROM playlists p
        WHERE p.id = %s
          AND p.user_id = %s
          AND pit.playlist_id = p.id
          AND pit.status <> 'await'
        RETURNING pit.id;
    """, (self.playlist_id, self.user_id), fetchall=True)
        items_reset = len(rows or [])

        if items_reset:
            logger.info("%s items in playlist %s reset to 'await'", items_reset, self.playlist_id)
        else:
            logger.info("No items in playlist %s needed reset", self.playlist_id)

        restarted = run_query("""
        UPDATE playlists p
        SET status = 'await', completed_at = NULL, last_sent = NULL
        WHERE p.id = %s
          AND p.user_id = %s
          AND p.status <> 'await'
        RETURNING p.id;
    """, (self.playlist_id, self.user_id), fetchone = True)

        if restarted:
            restarted_id = restarted[0]
            logger.info("Playlist %s restarted", restarted_id)
            msg = f"Playlist #{restarted_id} restarted.\nItems reset: {items_reset}."
            return {"playlist_id": restarted_id, "items_reset": items_reset, "msg": msg}
        else:
            logger.info("Playlist %s wasn't restarted (already 'await' or not found)", self.playlist_id)
            if items_reset > 0:
                msg = f"Items reset: {items_reset}.\nPlaylist status was already 'await'."
            else:
                msg = "Playlist not found or doesn't belong to you."
            return {"playlist_id": None, "items_reset": items_reset, "msg": msg}