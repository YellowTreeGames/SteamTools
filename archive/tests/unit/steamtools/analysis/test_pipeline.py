"""Unit tests for steamtools.analysis.pipeline — Gemini and DB fully mocked."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_db_steam():
    db = MagicMock()
    db.get_reviews.return_value = [
        {"recommendationid": 111, "review": "Great game!"},
        {"recommendationid": 222, "review": "Not bad."},
    ]
    return db


@pytest.fixture()
def mock_db_analysis():
    db = MagicMock()
    db.get_processed_review_ids.return_value = set()
    db.get_taxonomy.return_value = {"status": "ready"}
    db.get_taxonomy_for_classify.return_value = {"Gameplay": ["combat"], "Audio": ["background music"]}
    return db


@pytest.fixture()
def mock_aspects():
    aspect = MagicMock()
    aspect.model_dump.return_value = {
        "category": "Gameplay",
        "specific_feature": "combat",
        "sentiment": "Positive",
        "rationale": "Fun fights.",
    }
    return [aspect]


@pytest.fixture()
def mock_discovery(mock_aspects):
    pair = MagicMock()
    pair.category = "Gameplay"
    pair.feature = "combat"

    cat = MagicMock()
    cat.features = []
    cat.model_dump.return_value = {"name": "Gameplay", "is_seed": True, "features": []}
    return pair, cat


class TestRunAbsaPipeline:
    def test_raises_if_no_api_key(self, mock_db_steam, mock_db_analysis):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with patch("steamtools.analysis.pipeline.config") as mock_config:
            mock_config.GEMINI_API_KEY = None
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                run_absa_pipeline(1, mock_db_steam, mock_db_analysis)

    def test_processes_all_reviews(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis)
        assert result["processed"] == 2
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["taxonomy_built"] is False

    def test_skips_already_processed(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        mock_db_analysis.get_processed_review_ids.return_value = {111}
        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis)
        assert result["processed"] == 1
        assert result["skipped"] == 1

    def test_force_wipes_and_reruns(self, mock_db_steam, mock_db_analysis, mock_aspects, mock_discovery):
        from steamtools.analysis.pipeline import run_absa_pipeline

        mock_pair, mock_cat = mock_discovery
        mock_db_analysis.get_taxonomy.return_value = None
        mock_db_analysis.get_processed_review_ids.return_value = set()

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.discover_batch", return_value=([mock_pair], True)),
            patch("steamtools.analysis.pipeline.canonicalize_taxonomy", return_value=[mock_cat]),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis, force=True)

        mock_db_analysis.wipe_game_absa.assert_called_once_with(1)
        assert result["processed"] == 2
        assert result["taxonomy_built"] is True

    def test_counts_failures(self, mock_db_steam, mock_db_analysis):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", side_effect=RuntimeError("api error")),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis)
        assert result["failed"] == 2
        assert result["processed"] == 0

    def test_batch_size_limits_classify(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis, batch_size=1)
        assert result["processed"] == 1

    def test_sleeps_between_classify_calls(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep") as mock_sleep,
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            run_absa_pipeline(1, mock_db_steam, mock_db_analysis, delay=1.5)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)

    def test_saves_aspects_to_db(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            run_absa_pipeline(1, mock_db_steam, mock_db_analysis)
        assert mock_db_analysis.save_absa_result.call_count == 2

    def test_empty_review_text_handled(self, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        db_steam = MagicMock()
        db_steam.get_reviews.return_value = [{"recommendationid": 1, "review": None}]
        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects) as mock_analyze,
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            run_absa_pipeline(1, db_steam, mock_db_analysis)
        mock_analyze.assert_called_once()
        assert mock_analyze.call_args[0][0] == ""

    def test_taxonomy_passed_to_analyze_review(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        taxonomy = {"Gameplay": ["combat"], "Audio": ["background music"]}
        mock_db_analysis.get_taxonomy_for_classify.return_value = taxonomy

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects) as mock_analyze,
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            run_absa_pipeline(1, mock_db_steam, mock_db_analysis)

        for call in mock_analyze.call_args_list:
            assert call.kwargs["taxonomy"] == taxonomy

    def test_discovery_runs_when_no_taxonomy(self, mock_db_steam, mock_db_analysis, mock_aspects, mock_discovery):
        from steamtools.analysis.pipeline import run_absa_pipeline

        mock_pair, mock_cat = mock_discovery
        mock_db_analysis.get_taxonomy.return_value = None

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.discover_batch", return_value=([mock_pair], False)) as mock_discover,
            patch("steamtools.analysis.pipeline.canonicalize_taxonomy", return_value=[mock_cat]),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis, discovery_sample_size=2, discovery_batch_size=2)

        assert mock_discover.called
        mock_db_analysis.upsert_taxonomy.assert_called_once()
        mock_db_analysis.save_taxonomy_data.assert_called_once()
        assert result["taxonomy_built"] is True

    def test_discovery_early_stop(self, mock_db_steam, mock_db_analysis, mock_aspects, mock_discovery):
        from steamtools.analysis.pipeline import run_absa_pipeline

        mock_pair, mock_cat = mock_discovery
        mock_db_analysis.get_taxonomy.return_value = None

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.discover_batch", return_value=([mock_pair], True)) as mock_discover,
            patch("steamtools.analysis.pipeline.canonicalize_taxonomy", return_value=[mock_cat]),
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            run_absa_pipeline(1, mock_db_steam, mock_db_analysis, discovery_sample_size=100, discovery_batch_size=1)

        assert mock_discover.call_count == 1

    def test_discovery_skipped_when_taxonomy_ready(self, mock_db_steam, mock_db_analysis, mock_aspects):
        from steamtools.analysis.pipeline import run_absa_pipeline

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
            patch("steamtools.analysis.pipeline.discover_batch") as mock_discover,
            patch("steamtools.analysis.pipeline.canonicalize_taxonomy") as mock_canon,
            patch("steamtools.analysis.pipeline.analyze_review", return_value=mock_aspects),
            patch("steamtools.analysis.pipeline.time.sleep"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            result = run_absa_pipeline(1, mock_db_steam, mock_db_analysis)

        mock_discover.assert_not_called()
        mock_canon.assert_not_called()
        assert result["taxonomy_built"] is False

    def test_raises_if_no_reviewable_text_during_discovery(self, mock_db_analysis):
        from steamtools.analysis.pipeline import run_absa_pipeline

        db_steam = MagicMock()
        db_steam.get_reviews.return_value = [{"recommendationid": 1, "review": None}]
        mock_db_analysis.get_taxonomy.return_value = None

        with (
            patch("steamtools.analysis.pipeline.config") as mock_config,
            patch("steamtools.analysis.pipeline.genai.Client"),
        ):
            mock_config.GEMINI_API_KEY = "fake-key"
            with pytest.raises(ValueError, match="No reviews with text"):
                run_absa_pipeline(1, db_steam, mock_db_analysis)
