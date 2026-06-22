"""Tests for steamtools.ai.gemini_client."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import steamtools.ai.gemini_client as gc


def _make_client(text: str, mocker) -> None:
    mock_response = MagicMock()
    mock_response.text = text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mocker.patch("steamtools.ai.gemini_client._client", mock_client)


def _template(tmp_path: Path) -> Path:
    t = tmp_path / "prompt.j2"
    t.write_text("Evaluate {{ game_name }}: {{ short_description }}", encoding="utf-8")
    return t


def test_evaluate_success(mocker, tmp_path):
    _make_client(json.dumps({"score": 3.5, "rationale": "Good game."}), mocker)
    result = gc.evaluate("MyGame", "A fun game.", _template(tmp_path), "model-x")
    assert result["score"] == 3.5
    assert result["rationale"] == "Good game."


def test_evaluate_score_zero(mocker, tmp_path):
    _make_client(json.dumps({"score": 0.0, "rationale": "Terrible."}), mocker)
    result = gc.evaluate("Game", "Bad.", _template(tmp_path), "model-x")
    assert result["score"] == 0.0


def test_evaluate_score_five(mocker, tmp_path):
    _make_client(json.dumps({"score": 5.0, "rationale": "Perfect."}), mocker)
    result = gc.evaluate("Game", "Amazing.", _template(tmp_path), "model-x")
    assert result["score"] == 5.0


def test_evaluate_non_json_raises(mocker, tmp_path):
    _make_client("not json", mocker)
    with pytest.raises(ValueError, match="Non-JSON"):
        gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")


def test_evaluate_none_response_raises(mocker, tmp_path):
    _make_client("null", mocker)
    with pytest.raises(ValueError, match="Missing or non-numeric"):
        gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")


def test_evaluate_missing_score_raises(mocker, tmp_path):
    _make_client(json.dumps({"rationale": "No score here."}), mocker)
    with pytest.raises(ValueError, match="Missing or non-numeric"):
        gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")


def test_evaluate_score_out_of_range_raises(mocker, tmp_path):
    _make_client(json.dumps({"score": 6.0, "rationale": "Too high."}), mocker)
    with pytest.raises(ValueError, match="out of range"):
        gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")


def test_evaluate_score_not_half_boundary_raises(mocker, tmp_path):
    _make_client(json.dumps({"score": 3.3, "rationale": "Odd score."}), mocker)
    with pytest.raises(ValueError, match="multiple of 0.5"):
        gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")


def test_evaluate_missing_rationale_returns_empty(mocker, tmp_path):
    _make_client(json.dumps({"score": 2.0}), mocker)
    result = gc.evaluate("Game", "Desc.", _template(tmp_path), "model-x")
    assert result["rationale"] == ""
