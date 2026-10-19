"""Integration tests — live HTTP calls to the Steam API.

These verify that the Steam client correctly parses real Steam responses.
No API key required: get_app_details uses the public store endpoint.

Run with: uv run pytest -m integration

Target app: Ryder (appid 3283790)
Store page: https://store.steampowered.com/app/3283790/Ryder/
"""

import pytest

RYDER_APPID = 3283790


@pytest.mark.integration
def test_get_app_details_returns_non_none():
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None, "Steam returned no data for Ryder (appid 3283790)"


@pytest.mark.integration
def test_get_app_details_type_is_game():
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None
    assert data.get("type") == "game"


@pytest.mark.integration
def test_get_app_details_name_contains_ryder():
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None
    assert "ryder" in data["name"].lower()


@pytest.mark.integration
def test_get_app_details_required_fields_present():
    """All fields that StoDB._row_from_details accesses must be present in the live payload."""
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None
    for field in ("type", "name", "is_free", "developers", "publishers", "genres", "categories", "platforms"):
        assert field in data, f"Missing required field: {field}"


@pytest.mark.integration
def test_get_app_details_platforms_has_windows_key():
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None
    platforms = data.get("platforms", {})
    assert isinstance(platforms, dict)
    assert "windows" in platforms


@pytest.mark.integration
def test_get_app_details_developers_is_list():
    from steamtools.steam_client import get_app_details

    data = get_app_details(RYDER_APPID)
    assert data is not None
    assert isinstance(data["developers"], list)
    assert len(data["developers"]) > 0


@pytest.mark.integration
def test_get_app_details_unknown_appid_returns_none():
    """An appid that does not exist should return None, not raise."""
    from steamtools.steam_client import get_app_details

    result = get_app_details(9999999)
    assert result is None
