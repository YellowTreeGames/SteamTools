"""SQLite connection plumbing and schema for the analysis DB."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

ANALYSIS_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "analysis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS absa_processed (
    review_id INTEGER NOT NULL,
    appid INTEGER NOT NULL,
    analyzed_at TEXT NOT NULL,
    model TEXT NOT NULL,
    PRIMARY KEY (review_id, appid)
);
CREATE TABLE IF NOT EXISTS absa_aspects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    appid INTEGER NOT NULL,
    category TEXT NOT NULL,
    specific_feature TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    rationale TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS absa_taxonomy (
    appid INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    discovery_sample_size INTEGER NOT NULL,
    discovery_reviews_sampled INTEGER,
    early_stopped INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS absa_taxonomy_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appid INTEGER NOT NULL,
    name TEXT NOT NULL,
    is_seed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(appid, name)
);
CREATE TABLE IF NOT EXISTS absa_taxonomy_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appid INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    UNIQUE(appid, canonical_name),
    FOREIGN KEY (category_id) REFERENCES absa_taxonomy_categories(id)
);
"""


def init_db() -> None:
    ANALYSIS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection():
    conn = sqlite3.connect(ANALYSIS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
