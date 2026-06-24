"""Unit tests for steamtools_cli.reviews — StoDB fully mocked."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from steamtools_cli.cli import app

runner = CliRunner()

_REVIEW_SUMMARY = {
    "appid": 3283790,
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


def _mock_db(**overrides) -> MagicMock:
    db = MagicMock()
    db.review_stats.return_value = _REVIEW_STATS
    db.get_review_summary.return_value = _REVIEW_SUMMARY
    db.sync_reviews.return_value = {"status": "fetched", "summary": _REVIEW_SUMMARY, "reviews_fetched": 10}
    for attr, val in overrides.items():
        getattr(db, attr).return_value = val
    return db


class TestReviewsFetch:
    def test_exits_zero(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "fetch", "--appid", "3283790"])
        assert result.exit_code == 0

    def test_prints_fetched_count(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "fetch", "--appid", "3283790"])
        assert "10" in result.output

    def test_prints_score_and_totals(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "fetch", "--appid", "3283790"])
        assert "Very Positive" in result.output
        assert "800" in result.output
        assert "50" in result.output

    def test_already_current_prints_message(self):
        db = _mock_db()
        db.sync_reviews.return_value = {"status": "already_current", "summary": _REVIEW_SUMMARY, "reviews_fetched": 0}
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            result = runner.invoke(app, ["reviews", "fetch", "--appid", "3283790"])
        assert "already_current" in result.output

    def test_force_passed_to_sync(self):
        db = _mock_db()
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            runner.invoke(app, ["reviews", "fetch", "--appid", "3283790", "--force"])
        db.sync_reviews.assert_called_once_with(3283790, force=True, language="all", filter="recent")

    def test_language_flag_passed_to_sync(self):
        db = _mock_db()
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            runner.invoke(app, ["reviews", "fetch", "--appid", "3283790", "--language", "english"])
        db.sync_reviews.assert_called_once_with(3283790, force=False, language="english", filter="recent")

    def test_filter_flag_passed_to_sync(self):
        db = _mock_db()
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            runner.invoke(app, ["reviews", "fetch", "--appid", "3283790", "--filter", "all"])
        db.sync_reviews.assert_called_once_with(3283790, force=False, language="all", filter="all")

    def test_appid_required(self):
        result = runner.invoke(app, ["reviews", "fetch"])
        assert result.exit_code != 0


class TestReviewsInfo:
    def test_global_stats_exits_zero(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "info"])
        assert result.exit_code == 0

    def test_global_stats_printed(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "info"])
        assert "1200" in result.output
        assert "3" in result.output

    def test_never_when_last_fetched_is_none(self):
        db = _mock_db()
        db.review_stats.return_value = {**_REVIEW_STATS, "last_fetched": None}
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            result = runner.invoke(app, ["reviews", "info"])
        assert "never" in result.output

    def test_appid_summary_printed(self):
        with patch("steamtools_cli.reviews.StoDB", return_value=_mock_db()):
            result = runner.invoke(app, ["reviews", "info", "--appid", "3283790"])
        assert "Very Positive" in result.output
        assert "850" in result.output

    def test_appid_none_summary_prints_message(self):
        db = _mock_db()
        db.get_review_summary.return_value = None
        with patch("steamtools_cli.reviews.StoDB", return_value=db):
            result = runner.invoke(app, ["reviews", "info", "--appid", "9999"])
        assert "No review summary" in result.output
