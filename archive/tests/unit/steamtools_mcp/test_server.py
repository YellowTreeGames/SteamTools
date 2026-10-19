"""Unit tests for steamtools_mcp.server — StoDB and AnalysisDB fully mocked."""

from unittest.mock import MagicMock, patch

import steamtools_mcp.server as server_mod
from tests.conftest import RYDER_APPID

_STATUS = {
    "apps_total": 200,
    "apps_with_details": 150,
    "apps_missing_details": 50,
    "apps_last_fetched": "2025-01-15T00:00:00+00:00",
    "details_total": 150,
    "details_last_fetched": "2025-01-15T00:00:00+00:00",
}

_SEARCH_RESULTS = [
    {"appid": RYDER_APPID, "name": "Ryder", "has_details": 1},
]

_SYNC_RESULT = {
    "status": "game",
    "appid": RYDER_APPID,
    "row": {"name": "Ryder", "type": "game"},
    "detected_type": "game",
}


def _mock_db(**overrides) -> MagicMock:
    db = MagicMock()
    db.status.return_value = _STATUS
    db.search_apps.return_value = _SEARCH_RESULTS
    db.sync_app_details_one.return_value = _SYNC_RESULT
    db.sync_app_list.return_value = 500
    db.sync_app_details.return_value = 25
    for attr, val in overrides.items():
        getattr(db, attr).return_value = val
    return db


class TestStatusTool:
    def test_returns_stodb_status(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            result = server_mod.status()
        assert result == _STATUS

    def test_delegates_to_stodb(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.status()
        MockDB.return_value.status.assert_called_once()


class TestSearchGamesTool:
    def test_returns_search_results(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            result = server_mod.search_games("ryder")
        assert result == _SEARCH_RESULTS

    def test_passes_query_to_search_apps(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.search_games("half-life")
        MockDB.return_value.search_apps.assert_called_once_with("half-life")

    def test_empty_query_returns_all(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.search_games("")
        MockDB.return_value.search_apps.assert_called_once_with("")


class TestGetAppDetailsTool:
    def test_returns_sync_result(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            result = server_mod.get_app_details(RYDER_APPID)
        assert result == _SYNC_RESULT

    def test_passes_appid_and_force_false_by_default(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.get_app_details(RYDER_APPID)
        MockDB.return_value.sync_app_details_one.assert_called_once_with(RYDER_APPID, force=False)

    def test_passes_force_true_when_requested(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.get_app_details(RYDER_APPID, force=True)
        MockDB.return_value.sync_app_details_one.assert_called_once_with(RYDER_APPID, force=True)

    def test_not_a_game_result_passes_through(self):
        not_game = {"status": "not_a_game", "appid": 99, "row": None, "detected_type": "dlc"}
        db = _mock_db()
        db.sync_app_details_one.return_value = not_game
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            result = server_mod.get_app_details(99)
        assert result == not_game


class TestFetchAppListTool:
    def test_returns_upserted_count(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            result = server_mod.fetch_app_list()
        assert result == {"upserted": 500}

    def test_full_refresh_passes_none(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.fetch_app_list()
        MockDB.return_value.sync_app_list.assert_called_once_with(None)

    def test_partial_refresh_passes_count(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.fetch_app_list(count=200)
        MockDB.return_value.sync_app_list.assert_called_once_with(200)


class TestFetchAppDetailsTool:
    def test_returns_processed_count(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()):
            result = server_mod.fetch_app_details()
        assert result == {"processed": 25}

    def test_no_limit_passes_none(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.fetch_app_details()
        MockDB.return_value.sync_app_details.assert_called_once_with(limit=None)

    def test_count_sets_limit(self):
        with patch("steamtools_mcp.server.StoDB", return_value=_mock_db()) as MockDB:
            server_mod.fetch_app_details(count=50)
        MockDB.return_value.sync_app_details.assert_called_once_with(limit=50)


_SYNC_REVIEWS_RESULT = {
    "status": "fetched",
    "summary": {
        "total_reviews": 850,
        "total_positive": 800,
        "total_negative": 50,
        "review_score": 8,
        "review_score_desc": "Very Positive",
    },
    "reviews_fetched": 10,
}

_REVIEW_SUMMARY_ROW = {
    "appid": RYDER_APPID,
    "total_reviews": 850,
    "total_positive": 800,
    "total_negative": 50,
    "review_score": 8,
    "review_score_desc": "Very Positive",
    "fetched_at": "2025-01-15T00:00:00+00:00",
}


class TestFetchReviewsTool:
    def test_returns_sync_result(self):
        db = _mock_db()
        db.sync_reviews.return_value = _SYNC_REVIEWS_RESULT
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            result = server_mod.fetch_reviews(RYDER_APPID)
        assert result == _SYNC_REVIEWS_RESULT

    def test_passes_appid_force_language(self):
        db = _mock_db()
        db.sync_reviews.return_value = _SYNC_REVIEWS_RESULT
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            server_mod.fetch_reviews(RYDER_APPID, force=True, language="english")
        db.sync_reviews.assert_called_once_with(RYDER_APPID, force=True, language="english")

    def test_defaults_force_false_language_all(self):
        db = _mock_db()
        db.sync_reviews.return_value = _SYNC_REVIEWS_RESULT
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            server_mod.fetch_reviews(RYDER_APPID)
        db.sync_reviews.assert_called_once_with(RYDER_APPID, force=False, language="all")


class TestGetReviewSummaryTool:
    def test_returns_summary_row(self):
        db = _mock_db()
        db.get_review_summary.return_value = _REVIEW_SUMMARY_ROW
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            result = server_mod.get_review_summary(RYDER_APPID)
        assert result == _REVIEW_SUMMARY_ROW

    def test_passes_appid(self):
        db = _mock_db()
        db.get_review_summary.return_value = _REVIEW_SUMMARY_ROW
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            server_mod.get_review_summary(RYDER_APPID)
        db.get_review_summary.assert_called_once_with(RYDER_APPID)

    def test_returns_none_when_unavailable(self):
        db = _mock_db()
        db.get_review_summary.return_value = None
        with patch("steamtools_mcp.server.StoDB", return_value=db):
            result = server_mod.get_review_summary(99999)
        assert result is None


_ABSA_PIPELINE_RESULT = {"processed": 3, "skipped": 1, "failed": 0}
_ABSA_ASPECTS = [
    {
        "id": 1,
        "review_id": 111,
        "appid": RYDER_APPID,
        "category": "Gameplay",
        "specific_feature": "combat",
        "sentiment": "Positive",
        "rationale": "Fun.",
    },
]


class TestRunAbsaTool:
    def test_returns_pipeline_result(self):
        with (
            patch("steamtools_mcp.server.StoDB"),
            patch("steamtools_mcp.server.AnalysisDB"),
            patch("steamtools_mcp.server.run_absa_pipeline", return_value=_ABSA_PIPELINE_RESULT),
        ):
            result = server_mod.run_absa(RYDER_APPID)
        assert result == _ABSA_PIPELINE_RESULT

    def test_passes_appid_and_defaults(self):
        with (
            patch("steamtools_mcp.server.StoDB"),
            patch("steamtools_mcp.server.AnalysisDB"),
            patch("steamtools_mcp.server.run_absa_pipeline", return_value=_ABSA_PIPELINE_RESULT) as mock_pipeline,
        ):
            server_mod.run_absa(RYDER_APPID)
        call_kwargs = mock_pipeline.call_args
        assert call_kwargs[0][0] == RYDER_APPID
        assert call_kwargs[1]["force"] is False
        assert call_kwargs[1]["delay"] == 4.0

    def test_passes_force_and_delay(self):
        with (
            patch("steamtools_mcp.server.StoDB"),
            patch("steamtools_mcp.server.AnalysisDB"),
            patch("steamtools_mcp.server.run_absa_pipeline", return_value=_ABSA_PIPELINE_RESULT) as mock_pipeline,
        ):
            server_mod.run_absa(RYDER_APPID, force=True, delay=2.0)
        assert mock_pipeline.call_args[1]["force"] is True
        assert mock_pipeline.call_args[1]["delay"] == 2.0


class TestGetAbsaResultsTool:
    def test_returns_aspects(self):
        mock_adb = MagicMock()
        mock_adb.get_absa_aspects.return_value = _ABSA_ASPECTS
        with patch("steamtools_mcp.server.AnalysisDB", return_value=mock_adb):
            result = server_mod.get_absa_results(RYDER_APPID)
        assert result == _ABSA_ASPECTS

    def test_passes_appid_no_filters(self):
        mock_adb = MagicMock()
        mock_adb.get_absa_aspects.return_value = []
        with patch("steamtools_mcp.server.AnalysisDB", return_value=mock_adb):
            server_mod.get_absa_results(RYDER_APPID)
        mock_adb.get_absa_aspects.assert_called_once_with(RYDER_APPID, category=None, sentiment=None)

    def test_passes_category_filter(self):
        mock_adb = MagicMock()
        mock_adb.get_absa_aspects.return_value = []
        with patch("steamtools_mcp.server.AnalysisDB", return_value=mock_adb):
            server_mod.get_absa_results(RYDER_APPID, category="Gameplay")
        mock_adb.get_absa_aspects.assert_called_once_with(RYDER_APPID, category="Gameplay", sentiment=None)

    def test_passes_sentiment_filter(self):
        mock_adb = MagicMock()
        mock_adb.get_absa_aspects.return_value = []
        with patch("steamtools_mcp.server.AnalysisDB", return_value=mock_adb):
            server_mod.get_absa_results(RYDER_APPID, sentiment="Positive")
        mock_adb.get_absa_aspects.assert_called_once_with(RYDER_APPID, category=None, sentiment="Positive")
