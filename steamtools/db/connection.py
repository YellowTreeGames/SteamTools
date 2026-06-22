"""SQLite connection plumbing and schema for SteamTools."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_MIGRATIONS = [
    ("app_review_counts", "total_positive", "INTEGER"),
    ("app_review_counts", "total_negative", "INTEGER"),
    ("app_review_counts", "review_score", "INTEGER"),
    ("app_review_counts", "review_score_desc", "TEXT"),
    ("app_details", "detailed_description", "TEXT"),
    ("app_details", "about_the_game", "TEXT"),
    ("app_details", "supported_languages", "TEXT"),
    ("app_details", "header_image", "TEXT"),
    ("app_details", "website", "TEXT"),
    ("app_details", "required_age", "INTEGER"),
    ("app_details", "platforms_windows", "INTEGER"),
    ("app_details", "platforms_mac", "INTEGER"),
    ("app_details", "platforms_linux", "INTEGER"),
    ("app_details", "achievements_total", "INTEGER"),
    ("app_details", "price_discount_percent", "INTEGER"),
    ("app_details", "dlc", "TEXT"),
    ("app_details", "screenshots", "TEXT"),
    ("app_details", "movies", "TEXT"),
    ("app_details", "content_descriptors", "TEXT"),
    ("app_details", "background", "TEXT"),
]

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "steamtools.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    appid INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

-- Only ever holds rows where type = 'game'. Non-game appids are deleted from
-- `apps` once appdetails confirms their type, so they never appear here.
CREATE TABLE IF NOT EXISTS app_details (
    appid INTEGER PRIMARY KEY REFERENCES apps(appid),
    type TEXT NOT NULL,
    name TEXT,
    required_age INTEGER,
    is_free INTEGER,
    short_description TEXT,
    detailed_description TEXT,
    about_the_game TEXT,
    supported_languages TEXT,
    header_image TEXT,
    website TEXT,
    release_date TEXT,
    coming_soon INTEGER,
    developers TEXT,
    publishers TEXT,
    genres TEXT,
    categories TEXT,
    platforms_windows INTEGER,
    platforms_mac INTEGER,
    platforms_linux INTEGER,
    price_currency TEXT,
    price_initial INTEGER,
    price_final INTEGER,
    price_discount_percent INTEGER,
    metacritic_score INTEGER,
    achievements_total INTEGER,
    dlc TEXT,
    screenshots TEXT,
    movies TEXT,
    content_descriptors TEXT,
    background TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_types (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    medium        TEXT NOT NULL,
    template_file TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    appid       INTEGER NOT NULL REFERENCES apps(appid),
    eval_type   INTEGER NOT NULL REFERENCES eval_types(id),
    eval_number INTEGER NOT NULL,
    score       REAL NOT NULL,
    rationale   TEXT,
    model       TEXT NOT NULL,
    evaled_at   TEXT NOT NULL,
    UNIQUE(appid, eval_type, eval_number)
);

CREATE TABLE IF NOT EXISTS app_review_counts (
    appid              INTEGER PRIMARY KEY REFERENCES apps(appid),
    total_reviews      INTEGER NOT NULL,
    total_positive     INTEGER,
    total_negative     INTEGER,
    review_score       INTEGER,
    review_score_desc  TEXT,
    fetched_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_reviews (
    review_id TEXT PRIMARY KEY,
    appid INTEGER NOT NULL REFERENCES apps(appid),
    voted_up INTEGER,
    votes_up INTEGER,
    votes_funny INTEGER,
    weighted_vote_score REAL,
    steam_purchase INTEGER,
    received_for_free INTEGER,
    written_during_early_access INTEGER,
    author_playtime_forever INTEGER,
    author_playtime_last_two_weeks INTEGER,
    review TEXT NOT NULL,
    timestamp_created INTEGER,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_fetch_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appid INTEGER NOT NULL REFERENCES apps(appid),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    reviews_fetched INTEGER NOT NULL DEFAULT 0,
    last_cursor TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    filter TEXT NOT NULL DEFAULT 'all',
    max_reviews INTEGER
);

CREATE TABLE IF NOT EXISTS review_topic_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appid INTEGER NOT NULL REFERENCES apps(appid),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    reviews_embedded INTEGER NOT NULL DEFAULT 0,
    clusters_found INTEGER,
    noise_count INTEGER,
    embedding_model TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    hdbscan_params TEXT NOT NULL,
    chroma_collection TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES review_topic_runs(id),
    appid INTEGER NOT NULL REFERENCES apps(appid),
    cluster_label INTEGER NOT NULL,
    category_name TEXT,
    description TEXT,
    review_count INTEGER NOT NULL,
    sample_review_ids TEXT,
    centroid_vector TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_topic_assignments (
    review_id TEXT NOT NULL REFERENCES app_reviews(review_id),
    run_id INTEGER NOT NULL REFERENCES review_topic_runs(id),
    topic_id INTEGER REFERENCES review_topics(id),
    similarity_score REAL,
    is_noise INTEGER NOT NULL DEFAULT 0,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (review_id, run_id)
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO eval_types (id, name, medium, template_file) "
            "VALUES (1, 'Appeal', 'short_description', 'short_description_appeal.j2')"
        )
        for table, col, typ in _MIGRATIONS:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # column already exists


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
