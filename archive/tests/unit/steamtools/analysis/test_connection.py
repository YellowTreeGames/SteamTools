"""Unit tests for steamtools.analysis.connection."""

import sqlite3

import pytest


@pytest.fixture()
def tmp_analysis_db(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis_test.db"
    monkeypatch.setattr("steamtools.analysis.connection.ANALYSIS_DB_PATH", db_path)
    return db_path


class TestInitDb:
    def test_creates_db_file(self, tmp_analysis_db):
        from steamtools.analysis.connection import init_db

        init_db()
        assert tmp_analysis_db.exists()

    def test_creates_absa_processed_table(self, tmp_analysis_db):
        from steamtools.analysis.connection import get_connection, init_db

        init_db()
        with get_connection() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "absa_processed" in tables

    def test_creates_absa_aspects_table(self, tmp_analysis_db):
        from steamtools.analysis.connection import get_connection, init_db

        init_db()
        with get_connection() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "absa_aspects" in tables

    def test_idempotent_on_repeated_calls(self, tmp_analysis_db):
        from steamtools.analysis.connection import init_db

        init_db()
        init_db()  # should not raise


class TestGetConnection:
    def test_yields_connection(self, tmp_analysis_db):
        from steamtools.analysis.connection import get_connection, init_db

        init_db()
        with get_connection() as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_commits_on_exit(self, tmp_analysis_db):
        from steamtools.analysis.connection import get_connection, init_db

        init_db()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO absa_processed (review_id, appid, analyzed_at, model) VALUES (?, ?, ?, ?)",
                (1, 100, "2025-01-01T00:00:00+00:00", "gemini-2.0-flash"),
            )
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM absa_processed WHERE review_id=1").fetchone()
        assert row is not None
