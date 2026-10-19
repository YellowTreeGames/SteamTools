"""Unit tests for steamtools_cli.cli — StoDB fully mocked."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from steamtools_cli.cli import app

runner = CliRunner()


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.status.return_value = {"total": 100, "last_fetched": "2025-01-15T00:00:00+00:00"}
    db.sync_app_list.return_value = 100
    db.search_apps.return_value = [{"appid": 1, "name": "Half-Life"}]
    return db


class TestInfoCommand:
    def test_shows_total(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "100" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.status.return_value = {"total": 0, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info"])
        assert "never" in result.output


class TestFetchCommand:
    def test_prints_upserted_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch"])
        assert result.exit_code == 0
        assert "Upserted 100 apps." in result.output

    def test_full_refresh_passes_none_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch"])
        MockDB.return_value.sync_app_list.assert_called_once_with(None)

    def test_count_flag_passed_through(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch", "--count", "500"])
        MockDB.return_value.sync_app_list.assert_called_once_with(500)


class TestSearchCommand:
    def test_prints_matching_apps(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            result = runner.invoke(app, ["search", "half"])
        assert result.exit_code == 0
        assert "1\tHalf-Life" in result.output
        MockDB.return_value.search_apps.assert_called_once_with("half")

    def test_no_matches_prints_nothing(self):
        db = _mock_db()
        db.search_apps.return_value = []
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["search", "zzz"])
        assert result.exit_code == 0
        assert result.output == ""
