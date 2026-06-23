"""Unit tests for steamtools.db.connection — schema, init, and connection behaviour."""

import sqlite3

import steamtools.db.connection as conn_mod
from steamtools.db.connection import get_connection, init_db


class TestInitDb:
    def test_creates_apps_table(self, tmp_db):
        init_db()
        with get_connection() as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apps'").fetchone()
        assert row is not None

    def test_creates_app_details_table(self, tmp_db):
        init_db()
        with get_connection() as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_details'").fetchone()
        assert row is not None

    def test_drops_legacy_eval_results_table(self, tmp_db):
        with sqlite3.connect(conn_mod.DB_PATH) as c:
            c.execute("CREATE TABLE IF NOT EXISTS eval_results (id INTEGER PRIMARY KEY)")
        init_db()
        with get_connection() as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='eval_results'").fetchone()
        assert row is None

    def test_drops_legacy_app_reviews_table(self, tmp_db):
        with sqlite3.connect(conn_mod.DB_PATH) as c:
            c.execute("CREATE TABLE IF NOT EXISTS app_reviews (id INTEGER PRIMARY KEY)")
        init_db()
        with get_connection() as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_reviews'").fetchone()
        assert row is None

    def test_idempotent_second_call_does_not_raise(self, tmp_db):
        init_db()
        init_db()
        with get_connection() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "apps" in tables
        assert "app_details" in tables

    def test_creates_data_directory_if_missing(self, tmp_path, monkeypatch):
        nested = tmp_path / "deep" / "nested" / "test.db"
        monkeypatch.setattr("steamtools.db.connection.DB_PATH", nested)
        init_db()
        assert nested.exists()


class TestGetConnection:
    def test_yields_connection_with_row_factory(self, tmp_db):
        init_db()
        with get_connection() as conn:
            conn.execute("INSERT INTO apps (appid, name, last_seen_at) VALUES (1, 'Test', '2025-01-01')")
            row = conn.execute("SELECT * FROM apps WHERE appid = 1").fetchone()
        assert row["appid"] == 1
        assert row["name"] == "Test"

    def test_commits_on_clean_exit(self, tmp_db):
        init_db()
        with get_connection() as conn:
            conn.execute("INSERT INTO apps (appid, name, last_seen_at) VALUES (1, 'Test', '2025-01-01')")
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM apps WHERE appid = 1").fetchone()
        assert row is not None

    def test_does_not_commit_on_exception(self, tmp_db):
        init_db()
        try:
            with get_connection() as conn:
                conn.execute("INSERT INTO apps (appid, name, last_seen_at) VALUES (1, 'Test', '2025-01-01')")
                raise RuntimeError("forced failure")
        except RuntimeError:
            pass
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM apps WHERE appid = 1").fetchone()
        assert row is None
