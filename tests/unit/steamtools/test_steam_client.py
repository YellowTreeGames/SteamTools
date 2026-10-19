"""Unit tests for steamtools.steam_client — all HTTP calls mocked."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from steamtools.steam_client import get_app_list, get_app_list_page


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    mock = MagicMock(spec=requests.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.raise_for_status.return_value = None
    return mock


class TestGetAppListPage:
    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        expected_apps = [{"appid": 1, "name": "Game A"}, {"appid": 2, "name": "Game B"}]
        resp = _mock_response(200, {"response": {"apps": expected_apps, "have_more_results": False, "last_appid": 2}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_list_page()
        assert result["apps"] == expected_apps
        assert result["have_more_results"] is False
        assert result["last_appid"] == 2

    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", None)
        with pytest.raises(RuntimeError, match="STEAM_API_KEY"):
            get_app_list_page()

    def test_passes_last_appid_and_max_results(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        resp = _mock_response(200, {"response": {"apps": [], "have_more_results": False, "last_appid": 999}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            get_app_list_page(last_appid=500, max_results=100)
        params = mock_session.get.call_args.kwargs["params"]
        assert params["last_appid"] == 500
        assert params["max_results"] == 100

    def test_empty_response_defaults_apps_to_empty_list(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        resp = _mock_response(200, {"response": {}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_list_page()
        assert result["apps"] == []
        assert result["have_more_results"] is False

    def test_game_filter_flags_set_correctly(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        resp = _mock_response(200, {"response": {"apps": [], "have_more_results": False, "last_appid": 0}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            get_app_list_page()
        params = mock_session.get.call_args.kwargs["params"]
        assert params["include_games"] == "true"
        assert params["include_dlc"] == "false"
        assert params["include_software"] == "false"


class TestGetAppList:
    def test_single_page_no_more_results(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        apps = [{"appid": 1, "name": "A"}]
        resp = _mock_response(200, {"response": {"apps": apps, "have_more_results": False, "last_appid": 1}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_list()
        assert result == apps
        assert mock_session.get.call_count == 1

    def test_multiple_pages_aggregated(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        page1 = _mock_response(
            200, {"response": {"apps": [{"appid": 1, "name": "A"}], "have_more_results": True, "last_appid": 1}}
        )
        page2 = _mock_response(
            200, {"response": {"apps": [{"appid": 2, "name": "B"}], "have_more_results": False, "last_appid": 2}}
        )
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.side_effect = [page1, page2]
            result = get_app_list()
        assert len(result) == 2
        assert result[0]["appid"] == 1
        assert result[1]["appid"] == 2

    def test_second_page_uses_last_appid(self, monkeypatch):
        monkeypatch.setattr("steamtools.steam_client.STEAM_API_KEY", "fake-key")
        page1 = _mock_response(
            200, {"response": {"apps": [{"appid": 42, "name": "A"}], "have_more_results": True, "last_appid": 42}}
        )
        page2 = _mock_response(200, {"response": {"apps": [], "have_more_results": False, "last_appid": 42}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.side_effect = [page1, page2]
            get_app_list()
        second_params = mock_session.get.call_args_list[1].kwargs["params"]
        assert second_params["last_appid"] == 42
