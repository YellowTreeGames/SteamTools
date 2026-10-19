"""SQLite connection plumbing and schema for SteamTools."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_APP_DETAILS_MIGRATIONS = [
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

_DROP_TABLES = [
    "review_topic_assignments",
    "review_topics",
    "review_topic_runs",
    "review_fetch_sessions",
    "app_review_counts",
    "eval_results",
    "eval_types",
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

-- Aggregate review stats per game; one row per appid, refreshed every 7 days.
CREATE TABLE IF NOT EXISTS app_review_summary (
    appid INTEGER PRIMARY KEY REFERENCES apps(appid),
    total_reviews INTEGER,
    total_positive INTEGER,
    total_negative INTEGER,
    review_score INTEGER,
    review_score_desc TEXT,
    fetched_at TEXT NOT NULL
);

-- Individual review records; immutable once written (no deleted-review cleanup).
CREATE TABLE IF NOT EXISTS app_reviews (
    recommendationid INTEGER PRIMARY KEY,
    appid INTEGER NOT NULL REFERENCES apps(appid),
    author_steamid TEXT,
    author_num_games_owned INTEGER,
    author_num_reviews INTEGER,
    author_playtime_forever INTEGER,
    author_playtime_at_review INTEGER,
    language TEXT,
    review TEXT,
    timestamp_created INTEGER,
    timestamp_updated INTEGER,
    voted_up INTEGER,
    votes_up INTEGER,
    votes_funny INTEGER,
    weighted_vote_score REAL,
    comment_count INTEGER,
    steam_purchase INTEGER,
    received_for_free INTEGER,
    written_during_early_access INTEGER,
    fetched_at TEXT NOT NULL
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        for table in _DROP_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")  # noqa: S608
        conn.executescript(SCHEMA)
        for table, col, typ in _APP_DETAILS_MIGRATIONS:
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
