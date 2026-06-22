import pytest

from steamtools.db.connection import init_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a per-test temp file with a fresh schema."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("steamtools.db.connection.DB_PATH", db_path)
    init_db()
    yield db_path


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Suppress all time.sleep calls so tests run fast."""
    monkeypatch.setattr("steamtools.db.store.time.sleep", lambda _: None)
    monkeypatch.setattr("steamtools.steam_client.time.sleep", lambda _: None)
