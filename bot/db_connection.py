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


def mark_video_done(video_id, playlist_id, user_id):
    res = run_query("""
        UPDATE playlist_items AS pit
            SET status = 'done',
                completed_at = NOW()
            WHERE pit.id = %s
            AND pit.playlist_id = %s
            AND EXISTS (
                    SELECT 1
                    FROM playlists p
                    WHERE p.id = pit.playlist_id
                    AND p.user_id = %s
            )
            RETURNING pit.id;
""", (video_id, playlist_id, user_id), fetchone=True)
    return bool(res)


def resolve_playlist_arg(user_id, number):
    if not number:
        return None
    
    try:
        num = int(number)
    except ValueError:
        return None
    
    row = run_query("""
            WITH ordered AS (
                SELECT p.id, ROW_NUMBER() OVER (ORDER BY p.id) AS num
                FROM playlists p
                WHERE p.user_id = %s
                    AND p.youtube_link <> 'default_playlist'
            )
            SELECT id FROM ordered WHERE num = %s;
        """, (user_id, num), fetchone=True)
    return row[0] if row else None




        
    

