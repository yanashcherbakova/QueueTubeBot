import psycopg2
import os
import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_query(query, params=None, *, fetchone=False, fetchall=False):
    with psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432)
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                if fetchone:
                    result = cur.fetchone()       # tuple | None
                elif fetchall:
                    result = cur.fetchall()      # list[tuple]
                else:
                    result = None
            else:
                result = None
        logger.info("Query executed: %s | params=%s", query.strip().split("\n")[0], params)
        return result


def simple_insert(table_name, holders : int, column_name_list, conflict = 0, returning = 0, conflict_object = None , returning_object = None):
    text =  f"""
            INSERT INTO {table_name} ({", ".join(column_name_list)})
            VALUES ({", ".join(["%s"] * holders)})
"""
    if conflict == 1:
        text += f'\nON CONFLICT ({", ".join(conflict_object)}) DO NOTHING'
    if returning == 1:
        text += f'\nRETURNING {returning_object}'

    text += ';'
    return text
   

def get_or_create_default_playlist(user_id):
    column_name_list = ['user_id', 'youtube_link', 'title', 'full_duration', 'status']
    playlist_id = run_query(
        simple_insert('playlists', 5, column_name_list, 1, 1, ['user_id', 'youtube_link'], 'id'),
        (user_id, "default_playlist", "playlist_for_single_videos", 0, 'await'),
        fetchone=True
    )
    if not playlist_id:
        playlist_id = run_query("""
            SELECT id FROM playlists
            WHERE user_id = %s AND youtube_link = %s
            LIMIT 1;
        """, (user_id, "default_playlist"), fetchone=True)
    return playlist_id[0] if playlist_id else None




        
    

