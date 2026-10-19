"""Unit tests for general.analysis.absa.engine — Gemini client fully mocked."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_client():
    client = MagicMock()
    return client


def _make_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


class TestAnalyzeReview:
    def test_returns_aspects(self, mock_client):
        from general.analysis.absa.engine import analyze_review

        mock_client.models.generate_content.return_value = _make_response(
            '{"aspects": [{"category": "Gameplay", "specific_feature": "combat", "sentiment": "Positive", "rationale": "Fun."}]}'
        )
        aspects = analyze_review("Great game!", "test-model", mock_client)

        assert len(aspects) == 1
        assert aspects[0].category == "Gameplay"
        assert aspects[0].specific_feature == "combat"
        assert aspects[0].sentiment == "Positive"

    def test_returns_empty_aspects(self, mock_client):
        from general.analysis.absa.engine import analyze_review

        mock_client.models.generate_content.return_value = _make_response('{"aspects": []}')
        aspects = analyze_review("meh", "test-model", mock_client)

        assert aspects == []

    def test_taxonomy_included_in_system_prompt(self, mock_client):
        from general.analysis.absa.engine import analyze_review

        mock_client.models.generate_content.return_value = _make_response('{"aspects": []}')
        taxonomy = {"Gameplay": ["combat", "puzzles"], "Audio": ["background music"]}
        analyze_review("Great!", "test-model", mock_client, taxonomy=taxonomy)

        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert "combat" in config.system_instruction
        assert "background music" in config.system_instruction

    def test_no_taxonomy_uses_seed_categories(self, mock_client):
        from general.analysis.absa.engine import SEED_CATEGORIES, analyze_review

        mock_client.models.generate_content.return_value = _make_response('{"aspects": []}')
        analyze_review("Great!", "test-model", mock_client, taxonomy=None)

        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert SEED_CATEGORIES[0] in config.system_instruction

    def test_truncates_text_to_2000_chars(self, mock_client):
        from general.analysis.absa.engine import analyze_review

        mock_client.models.generate_content.return_value = _make_response('{"aspects": []}')
        analyze_review("x" * 5000, "test-model", mock_client)

        user_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
        assert len(user_prompt) <= 2100


class TestDiscoverBatch:
    def test_returns_pairs_and_flag(self, mock_client):
        from general.analysis.absa.engine import discover_batch

        mock_client.models.generate_content.return_value = _make_response(
            '{"pairs": [{"category": "Gameplay", "feature": "combat"}], "taxonomy_complete": false}'
        )
        pairs, done = discover_batch(["Great game!"], {}, mock_client, "test-model")

        assert len(pairs) == 1
        assert pairs[0].category == "Gameplay"
        assert pairs[0].feature == "combat"
        assert done is False

    def test_early_stop_true(self, mock_client):
        from general.analysis.absa.engine import discover_batch

        mock_client.models.generate_content.return_value = _make_response('{"pairs": [], "taxonomy_complete": true}')
        _, done = discover_batch(["Short."], {}, mock_client, "test-model")

        assert done is True

    def test_accumulated_passed_to_prompt(self, mock_client):
        from general.analysis.absa.engine import discover_batch

        mock_client.models.generate_content.return_value = _make_response('{"pairs": [], "taxonomy_complete": false}')
        accumulated = {"Gameplay": ["combat"]}
        discover_batch(["review"], accumulated, mock_client, "test-model")

        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert "combat" in config.system_instruction


class TestCanonicalizeTaxonomy:
    def test_returns_canonical_categories(self, mock_client):
        from general.analysis.absa.engine import canonicalize_taxonomy

        mock_client.models.generate_content.return_value = _make_response(
            '{"categories": [{"name": "Gameplay", "is_seed": true, "features": '
            '[{"canonical_name": "puzzle design", "aliases": ["puzzle mechanics", "puzzles"]}]}]}'
        )
        raw = {"Gameplay": ["puzzle mechanics", "puzzles", "puzzle design"]}
        categories = canonicalize_taxonomy(raw, mock_client, "test-model")

        assert len(categories) == 1
        assert categories[0].name == "Gameplay"
        assert categories[0].is_seed is True
        assert categories[0].features[0].canonical_name == "puzzle design"
        assert "puzzle mechanics" in categories[0].features[0].aliases

    def test_returns_empty_when_no_pairs(self, mock_client):
        from general.analysis.absa.engine import canonicalize_taxonomy

        mock_client.models.generate_content.return_value = _make_response('{"categories": []}')
        categories = canonicalize_taxonomy({}, mock_client, "test-model")

        assert categories == []
