"""Unit tests for steamtools.steam_client — all HTTP calls mocked."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from steamtools.steam_client import get_app_details, get_app_list, get_app_list_page, get_app_reviews


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


class TestGetAppDetails:
    def test_happy_path_returns_data(self):
        data = {"type": "game", "name": "Test Game"}
        resp = _mock_response(200, {"3283790": {"success": True, "data": data}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_details(3283790)
        assert result == data

    def test_success_false_returns_none(self):
        resp = _mock_response(200, {"3283790": {"success": False}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_details(3283790)
        assert result is None

    def test_appid_absent_from_response_returns_none(self):
        resp = _mock_response(200, {})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_details(3283790)
        assert result is None

    def test_retries_on_429_then_succeeds(self):
        data = {"type": "game", "name": "Retried Game"}
        rate_limited = _mock_response(429)
        ok = _mock_response(200, {"1": {"success": True, "data": data}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.side_effect = [rate_limited, ok]
            with patch("steamtools.steam_client.time.sleep"):
                result = get_app_details(1)
        assert result == data
        assert mock_session.get.call_count == 2

    def test_all_retries_exhausted_raises(self):
        rate_limited = _mock_response(429)
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = rate_limited
            with patch("steamtools.steam_client.time.sleep"):
                with pytest.raises(RuntimeError, match="rate-limited"):
                    get_app_details(1, max_retries=2)
        assert mock_session.get.call_count == 2

    def test_sends_correct_params(self):
        resp = _mock_response(200, {"99": {"success": True, "data": {"type": "game"}}})
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            get_app_details(99)
        params = mock_session.get.call_args.kwargs["params"]
        assert params["appids"] == 99
        assert params["cc"] == "us"
        assert params["l"] == "english"


class TestGetAppReviews:
    _REVIEW_PAYLOAD = {
        "success": 1,
        "query_summary": {
            "total_reviews": 100,
            "total_positive": 90,
            "total_negative": 10,
            "review_score": 8,
            "review_score_desc": "Very Positive",
        },
        "reviews": [{"recommendationid": "1"}],
        "cursor": "nextcursor",
    }

    def test_happy_path_returns_full_payload(self):
        resp = _mock_response(200, self._REVIEW_PAYLOAD)
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            result = get_app_reviews(3283790)
        assert result["success"] == 1
        assert result["query_summary"]["total_reviews"] == 100
        assert result["cursor"] == "nextcursor"

    def test_sends_correct_params(self):
        resp = _mock_response(200, self._REVIEW_PAYLOAD)
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            get_app_reviews(3283790, cursor="abc", language="english", filter="recent", num_per_page=50)
        params = mock_session.get.call_args.kwargs["params"]
        assert params["json"] == 1
        assert params["cursor"] == "abc"
        assert params["language"] == "english"
        assert params["filter"] == "recent"
        assert params["num_per_page"] == 50
        assert params["review_type"] == "all"
        assert params["purchase_type"] == "all"

    def test_url_includes_appid(self):
        resp = _mock_response(200, self._REVIEW_PAYLOAD)
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.return_value = resp
            get_app_reviews(9999)
        url = mock_session.get.call_args.args[0]
        assert "9999" in url

    def test_retries_on_429(self):
        rate_limited = _mock_response(429)
        ok = _mock_response(200, self._REVIEW_PAYLOAD)
        with patch("steamtools.steam_client._session") as mock_session:
            mock_session.get.side_effect = [rate_limited, ok]
            with patch("steamtools.steam_client.time.sleep"):
                result = get_app_reviews(1)
        assert result["success"] == 1
        assert mock_session.get.call_count == 2
