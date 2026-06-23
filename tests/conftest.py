"""Shared pytest fixtures and test data constants."""

import pytest

RYDER_APPID = 3283790

# Representative Steam API payload for Ryder (appid 3283790).
# Used by unit tests to avoid live network calls.
RYDER_STEAM_DATA: dict = {
    "type": "game",
    "name": "Ryder",
    "steam_appid": RYDER_APPID,
    "required_age": 0,
    "is_free": False,
    "short_description": "An action game.",
    "detailed_description": "<p>Detailed description.</p>",
    "about_the_game": "<p>About the game.</p>",
    "supported_languages": "English",
    "header_image": "https://cdn.cloudflare.steamstatic.com/steam/apps/3283790/header.jpg",
    "website": None,
    "release_date": {"coming_soon": False, "date": "Jan 1, 2024"},
    "developers": ["Ryder Studios"],
    "publishers": ["Ryder Publishing"],
    "genres": [{"id": "1", "description": "Action"}],
    "categories": [{"id": "2", "description": "Single-player"}],
    "platforms": {"windows": True, "mac": False, "linux": False},
    "price_overview": {
        "currency": "USD",
        "initial": 999,
        "final": 999,
        "discount_percent": 0,
    },
    "metacritic": None,
    "achievements": {"total": 5},
    "dlc": [],
    "screenshots": [],
    "movies": [],
    "content_descriptors": {},
    "background": "https://cdn.cloudflare.steamstatic.com/steam/apps/3283790/page_bg.jpg",
}


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Patch DB_PATH to a fresh temp file so every test gets its own isolated SQLite DB."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("steamtools.db.connection.DB_PATH", db_path)
    yield db_path


@pytest.fixture()
def fresh_db(tmp_db):
    """Initialized StoDB backed by the temp DB, with zero inter-request sleep."""
    from steamtools.db.store import StoDB

    return StoDB(details_sleep=0)
