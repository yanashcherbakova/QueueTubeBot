CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE playlists (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    youtube_link TEXT NOT NULL,
    title TEXT,
    full_duration INT,
    status TEXT DEFAULT 'await',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_sent timestamptz,
    completed_at timestamptz
);

CREATE TABLE playlist_items (
    id SERIAL PRIMARY KEY,
    playlist_id BIGINT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position_num INT,
    title TEXT,
    link TEXT NOT NULL,
    duration_sec INT,
    status TEXT DEFAULT 'await',
    completed_at timestamptz
);

CREATE INDEX idx_playlists_user_id ON playlists(user_id);
CREATE INDEX idx_items_playlist_id_pos ON playlist_items(playlist_id, position_num);
CREATE INDEX idx_items_link ON playlist_items(link);