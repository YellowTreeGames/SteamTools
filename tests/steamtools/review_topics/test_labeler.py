"""Tests for steamtools.review_topics.labeler."""

import json
from unittest.mock import MagicMock

from steamtools.review_topics.labeler import ClusterLabeler


def _make_labeler(response_text: str, mocker) -> tuple[ClusterLabeler, MagicMock]:
    mock_resp = MagicMock()
    mock_resp.text = response_text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    mocker.patch("steamtools.ai.gemini_client._client", mock_client)
    return ClusterLabeler(model_name="test-model"), mock_client


def test_label_cluster_success(mocker):
    payload = {"category_name": "Gameplay Issues", "description": "Reviews about bugs."}
    labeler, _ = _make_labeler(json.dumps(payload), mocker)
    result = labeler.label_cluster(["Bug in level 3", "Game crashes often"])
    assert result["category_name"] == "Gameplay Issues"
    assert result["description"] == "Reviews about bugs."


def test_label_cluster_truncates_to_10_reviews(mocker):
    payload = {"category_name": "T", "description": "D"}
    labeler, mock_client = _make_labeler(json.dumps(payload), mocker)
    reviews = [f"review {i}" for i in range(20)]
    labeler.label_cluster(reviews)
    # Only first 10 should appear in the prompt — verified via mock args
    call_kwargs = mock_client.models.generate_content.call_args
    prompt = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "review 10" not in prompt


def test_label_cluster_json_decode_error_returns_unknown(mocker):
    labeler, _ = _make_labeler("not valid json", mocker)
    result = labeler.label_cluster(["some review"])
    assert result["category_name"] == "Unknown"
    assert result["description"] == ""


def test_label_cluster_missing_keys_returns_defaults(mocker):
    labeler, _ = _make_labeler("{}", mocker)
    result = labeler.label_cluster(["review"])
    assert result["category_name"] == "Unknown"
    assert result["description"] == ""
