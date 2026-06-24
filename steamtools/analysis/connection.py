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
