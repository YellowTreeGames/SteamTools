"""Unit tests for steamtools_cli — StoDB fully mocked, no DB or Steam calls."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from steamtools_cli.cli import _make_progress_logger, app

runner = CliRunner()

_APP_STATS = {
    "total": 100,
    "with_details": 60,
    "last_fetched": "2025-01-15T00:00:00+00:00",
}
_DETAILS_STATS = {
    "total": 60,
    "last_fetched": "2025-01-15T00:00:00+00:00",
}
_REVIEW_SUMMARY = {
    "appid": 10,
    "total_reviews": 850,
    "total_positive": 800,
    "total_negative": 50,
    "review_score": 8,
    "review_score_desc": "Very Positive",
    "fetched_at": "2025-01-15T00:00:00+00:00",
}
_REVIEW_STATS = {
    "games_with_reviews": 3,
    "total_reviews": 1200,
    "last_fetched": "2025-01-15T00:00:00+00:00",
}


def _mock_db(**method_overrides) -> MagicMock:
    db = MagicMock()
    db.app_stats.return_value = _APP_STATS
    db.app_details_stats.return_value = _DETAILS_STATS
    db.review_stats.return_value = _REVIEW_STATS
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


class TestInfoCommand:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info"])
        assert result.exit_code == 0

    def test_shows_apps_total(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info"])
        assert "100" in result.output

    def test_shows_with_details_and_missing(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info"])
        assert "60" in result.output
        assert "40" in result.output

    def test_shows_review_stats(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info"])
        assert "1200" in result.output
        assert "3" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.app_stats.return_value = {**_APP_STATS, "last_fetched": None}
        db.app_details_stats.return_value = {**_DETAILS_STATS, "last_fetched": None}
        db.review_stats.return_value = {**_REVIEW_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info"])
        assert "never" in result.output


class TestInfoAppFlag:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--app"])
        assert result.exit_code == 0

    def test_shows_total_and_with_details(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--app"])
        assert "100" in result.output
        assert "60" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.app_stats.return_value = {**_APP_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info", "--app"])
        assert "never" in result.output


class TestInfoAppDetailsFlag:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--app-details"])
        assert result.exit_code == 0

    def test_shows_total(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--app-details"])
        assert "60" in result.output

    def test_shows_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.app_details_stats.return_value = {**_DETAILS_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info", "--app-details"])
        assert "never" in result.output


class TestInfoReviewsFlag:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--reviews"])
        assert result.exit_code == 0

    def test_global_stats_printed(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--reviews"])
        assert "3" in result.output
        assert "1200" in result.output

    def test_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.review_stats.return_value = {**_REVIEW_STATS, "last_fetched": None}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info", "--reviews"])
        assert "never" in result.output

    def test_appid_summary_printed(self):
        db = _mock_db()
        db.get_review_summary.return_value = _REVIEW_SUMMARY
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info", "--reviews", "--appid", "3283790"])
        assert "Very Positive" in result.output
        assert "850" in result.output

    def test_appid_none_summary_prints_message(self):
        db = _mock_db()
        db.get_review_summary.return_value = None
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["info", "--reviews", "--appid", "9999"])
        assert "No review summary" in result.output

    def test_appid_without_reviews_flag_exits_nonzero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["info", "--appid", "123"])
        assert result.exit_code != 0


class TestFetchCommand:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch"])
        assert result.exit_code == 0

    def test_fetches_app_list_with_full_refresh(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch"])
        MockDB.return_value.sync_app_list.assert_called_once_with(None)

    def test_fetches_pending_details(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch"])
        MockDB.return_value.sync_app_details.assert_called_once()

    def test_prints_both_outputs(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch"])
        assert "Upserted" in result.output
        assert "Processed" in result.output


class TestFetchAppFlag:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch", "--app"])
        assert result.exit_code == 0

    def test_prints_upserted_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch", "--app"])
        assert "Upserted 100 apps." in result.output

    def test_full_refresh_passes_none_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch", "--app"])
        MockDB.return_value.sync_app_list.assert_called_once_with(None)

    def test_count_flag_passed_through(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            result = runner.invoke(app, ["fetch", "--app", "--count", "500"])
        assert result.exit_code == 0
        MockDB.return_value.sync_app_list.assert_called_once_with(500)


class TestFetchAppDetailsFlag:
    def test_exits_zero(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch", "--app-details"])
        assert result.exit_code == 0

    def test_batch_prints_processed_count(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch", "--app-details"])
        assert "Processed 5 apps." in result.output

    def test_batch_count_flag_sets_limit(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            runner.invoke(app, ["fetch", "--app-details", "--count", "10"])
        assert MockDB.return_value.sync_app_details.call_args.kwargs["limit"] == 10

    def test_sleep_flag_sets_details_sleep(self):
        with patch("steamtools_cli.cli.StoDB") as MockStoDB:
            MockStoDB.return_value.sync_app_details.return_value = 0
            runner.invoke(app, ["fetch", "--app-details", "--sleep", "3.5"])
        assert MockStoDB.call_args.kwargs["details_sleep"] == 3.5

    def test_single_appid_game_output(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["fetch", "--app-details", "--appid", "10"])
        assert result.exit_code == 0
        assert "status=game" in result.output
        assert "name=Test Game" in result.output

    def test_single_appid_not_a_game_output(self):
        db = _mock_db()
        db.sync_app_details_one.return_value = {"status": "not_a_game", "appid": 10, "row": None, "detected_type": "dlc"}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["fetch", "--app-details", "--appid", "10"])
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
            result = runner.invoke(app, ["fetch", "--app-details", "--appid", "10"])
        assert result.exit_code == 0
        assert "already_current" in result.output

    def test_force_with_appid_passes_force_true(self):
        with patch("steamtools_cli.cli.StoDB", return_value=_mock_db()) as MockDB:
            result = runner.invoke(app, ["fetch", "--app-details", "--appid", "10", "--force"])
        assert result.exit_code == 0
        MockDB.return_value.sync_app_details_one.assert_called_once_with(10, force=True)

    def test_force_without_appid_exits_nonzero(self):
        result = runner.invoke(app, ["fetch", "--app-details", "--force"])
        assert result.exit_code != 0

    def test_appid_and_count_mutually_exclusive(self):
        result = runner.invoke(app, ["fetch", "--app-details", "--appid", "10", "--count", "5"])
        assert result.exit_code != 0

    def test_appid_without_app_details_flag_exits_nonzero(self):
        result = runner.invoke(app, ["fetch", "--app", "--appid", "10"])
        assert result.exit_code != 0


class TestFetchReviewsFlag:
    def test_exits_zero(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 10}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790"])
        assert result.exit_code == 0

    def test_prints_fetched_count(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 42}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790"])
        assert "42" in result.output

    def test_prints_score_and_totals(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 1}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790"])
        assert "Very Positive" in result.output
        assert "800" in result.output
        assert "50" in result.output

    def test_already_current_prints_message(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "already_current", "summary": _REVIEW_SUMMARY, "reviews_fetched": 0}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            result = runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790"])
        assert "already_current" in result.output

    def test_force_passed_to_sync(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 1}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790", "--force"])
        db.sync_reviews.assert_called_once_with(3283790, force=True, language="all")

    def test_language_flag_passed_to_sync(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 1}
        with patch("steamtools_cli.cli.StoDB", return_value=db):
            runner.invoke(app, ["fetch", "--reviews", "--appid", "3283790", "--language", "english"])
        db.sync_reviews.assert_called_once_with(3283790, force=False, language="english")

    def test_reviews_without_appid_exits_nonzero(self):
        result = runner.invoke(app, ["fetch", "--reviews"])
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
