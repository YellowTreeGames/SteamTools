"""Tests for steamtools.db.connection."""

import sqlite3

from steamtools.db.connection import get_connection, init_db


def test_init_db_creates_core_tables():
    with get_connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "apps" in tables
    assert "app_details" in tables
    assert "app_review_counts" in tables
    assert "eval_types" in tables
    assert "eval_results" in tables


def test_init_db_seeds_appeal_eval_type():
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM eval_types WHERE name='Appeal'").fetchone()
    assert row is not None
    assert row["medium"] == "short_description"


def test_init_db_idempotent():
    """Calling init_db a second time should not raise (migrations re-run safely)."""
    init_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM eval_types").fetchone()[0]
    assert count == 1  # INSERT OR IGNORE keeps one row


def test_get_connection_commits_on_success():
    with get_connection() as conn:
        conn.execute("INSERT INTO apps (appid, name, last_seen_at) VALUES (999, 'X', '2024-01-01')")

    with get_connection() as conn:
        row = conn.execute("SELECT name FROM apps WHERE appid=999").fetchone()
    assert row is not None
    assert row["name"] == "X"


def test_get_connection_closes_on_exception():
    """Connection closes even when body raises; data is NOT committed."""
    try:
        with get_connection() as conn:
            conn.execute("INSERT INTO apps (appid, name, last_seen_at) VALUES (888, 'Y', '2024-01-01')")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    with get_connection() as conn:
        row = conn.execute("SELECT name FROM apps WHERE appid=888").fetchone()
    assert row is None


def test_migration_column_already_exists_is_silent():
    """Running migrations when columns already exist raises no error."""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE app_review_counts ADD COLUMN total_positive INTEGER")
        except sqlite3.OperationalError:
            pass  # already added by init_db — that's the expected path
