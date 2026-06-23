"""Unit tests for steamtools_cli — StoDB fully mocked, no DB or Steam calls."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from steamtools_cli.cli import _make_progress_logger, app

runner = CliRunner()

_STATUS = {
    "apps_total": 100,
    "apps_with_details": 60,
    "apps_missing_details": 40,
    "apps_last_fetched": "2025-01-15T00:00:00+00:00",
    "details_total": 60,
    "details_last_fetched": "2025-01-15T00:00:00+00:00",
}
_APP_STATS = {
    "total": 100,
    "with_details": 60,
    "last_fetched": "2025-01-15T00:00:00+00:00",
}
_DETAILS_STATS = {
    "total": 60,
    "last_fetched": "2025-01-15T00:00:00+00:00",
}


def _mock_db(**method_overrides) -> MagicMock:
    db = MagicMock()
    db.status.return_value = _STATUS
    db.app_stats.return_value = _APP_STATS
    db.app_details_stats.return_value = _DETAILS_STATS
    db.sync_app_list.return_value = 100
    db.sync_app_details.return_value = 5
    db.sync_app_details_one.return_value = {
        "status": "game",
        "appid": 10,
        "row": {"name": "Test Game"},
        "detected_type": "game",
    }
    for attr, val in method_overrides.items():
        getattr(db, attr).return_value = val
    return db


class TestStatusCommand:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_shows_apps_total(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["status"])
        assert "100" in result.output

    def test_shows_with_details_and_missing(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["status"])
        assert "60" in result.output
        assert "40" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.status.return_value = {**_STATUS, "apps_last_fetched": None, "details_last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["status"])
        assert "never" in result.output


class TestAppInfoCommand:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app", "info"])
        assert result.exit_code == 0

    def test_shows_total_and_with_details(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app", "info"])
        assert "100" in result.output
        assert "60" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.app_stats.return_value = {**_APP_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["app", "info"])
        assert "never" in result.output


class TestAppFetchCommand:
    def test_full_refresh_prints_upserted_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app", "fetch"])
        assert result.exit_code == 0
        assert "Upserted 100 apps." in result.output

    def test_full_refresh_passes_none_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["app", "fetch"])
        MockDB.return_value.sync_app_list.assert_called_once_with(None)

    def test_count_flag_passed_through(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            result = runner.invoke(app, ["app", "fetch", "--count", "500"])
        assert result.exit_code == 0
        MockDB.return_value.sync_app_list.assert_called_once_with(500)


class TestAppDetailsInfoCommand:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app-details", "info"])
        assert result.exit_code == 0

    def test_shows_total(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app-details", "info"])
        assert "60" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.app_details_stats.return_value = {**_DETAILS_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["app-details", "info"])
        assert "never" in result.output


class TestDetailsFetchCommand:
    def test_batch_prints_processed_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app-details", "fetch"])
        assert result.exit_code == 0
        assert "Processed 5 apps." in result.output

    def test_batch_count_flag_sets_limit(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["app-details", "fetch", "--count", "10"])
        assert MockDB.return_value.sync_app_details.call_args.kwargs["limit"] == 10

    def test_sleep_flag_sets_details_sleep(self):
        with patch("steamtools_cli.cli.StoDB") as MockStoDB:
            MockStoDB.return_value.sync_app_details.return_value = 0
            runner.invoke(app, ["app-details", "fetch", "--sleep", "3.5"])
        assert MockStoDB.call_args.kwargs["details_sleep"] == 3.5

    def test_single_appid_game_output(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["app-details", "fetch", "--appid", "10"])
        assert result.exit_code == 0
        assert "status=game" in result.output
        assert "name=Test Game" in result.output

    def test_single_appid_not_a_game_output(self):
        db = _mock_db()
        db.sync_app_details_one.return_value = {"status": "not_a_game", "appid": 10, "row": None, "detected_type": "dlc"}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["app-details", "fetch", "--appid", "10"])
        assert result.exit_code == 0
        assert "status=not_a_game" in result.output
        assert "dlc" in result.output

    def test_single_appid_already_current_output(self):
        db = _mock_db()
        db.sync_app_details_one.return_value = {
            "status": "already_current",
            "appid": 10,
            "row": {"name": "Test"},
            "detected_type": None,
        }
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["app-details", "fetch", "--appid", "10"])
        assert result.exit_code == 0
        assert "already_current" in result.output

    def test_force_with_appid_passes_force_true(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            result = runner.invoke(app, ["app-details", "fetch", "--appid", "10", "--force"])
        assert result.exit_code == 0
        MockDB.return_value.sync_app_details_one.assert_called_once_with(10, force=True)

    def test_force_without_appid_exits_nonzero(self):
        result = runner.invoke(app, ["app-details", "fetch", "--force"])
        assert result.exit_code != 0

    def test_appid_and_count_mutually_exclusive(self):
        result = runner.invoke(app, ["app-details", "fetch", "--appid", "10", "--count", "5"])
        assert result.exit_code != 0


class TestProgressLogger:
    def test_logs_at_every_interval(self, capsys):
        logger = _make_progress_logger(2, lambda d: d["status"])
        logger(1, 4, 100, {"status": "game"})  # 1%2 != 0 and 1 != 4 → silent
        logger(2, 4, 200, {"status": "game"})  # 2%2 == 0 → output
        logger(3, 4, 300, {"status": "game"})  # 3%2 != 0 → silent
        logger(4, 4, 400, {"status": "game"})  # 4 == total → output
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
        assert len(lines) == 2
        assert "appid=200" in lines[0]
        assert "appid=400" in lines[1]

    def test_final_item_always_logged_regardless_of_interval(self, capsys):
        logger = _make_progress_logger(100, lambda d: d["status"])
        logger(1, 1, 999, {"status": "game"})
        assert "999" in capsys.readouterr().out

    def test_status_fn_applied_to_data(self, capsys):
        logger = _make_progress_logger(1, lambda d: f"type={d['type']}")
        logger(1, 1, 42, {"type": "dlc"})
        assert "type=dlc" in capsys.readouterr().out

    def test_position_info_in_output(self, capsys):
        logger = _make_progress_logger(1, lambda d: "ok")
        logger(3, 10, 55, {"status": "game"})
        out = capsys.readouterr().out
        assert "[3/10]" in out
        assert "appid=55" in out
