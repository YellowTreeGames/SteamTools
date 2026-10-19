"""Unit tests for steamtools_mcp.server — StoDB fully mocked."""

from unittest.mock import MagicMock, patch

from steamtools_mcp import server


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.status.return_value = {"total": 3, "last_fetched": None}
    db.search_apps.return_value = [{"appid": 1, "name": "A"}]
    db.sync_app_list.return_value = 42
    return db


class TestTools:
    def test_status_returns_db_status(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            assert server.status() == {"total": 3, "last_fetched": None}

    def test_search_games_delegates_query(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            result = server.search_games("a")
        assert result == [{"appid": 1, "name": "A"}]
        MockDB.return_value.search_apps.assert_called_once_with("a")

    def test_fetch_app_list_wraps_count_in_upserted(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            result = server.fetch_app_list(count=10)
        assert result == {"upserted": 42}
        MockDB.return_value.sync_app_list.assert_called_once_with(10)
