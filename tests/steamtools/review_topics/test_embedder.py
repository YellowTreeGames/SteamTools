"""Tests for steamtools.review_topics.embedder."""

import numpy as np
import pytest

from steamtools.review_topics.embedder import ReviewEmbedder


@pytest.fixture
def embedder(mocker):
    mock_model = mocker.MagicMock()
    mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer", return_value=mock_model)
    return ReviewEmbedder()


def test_embed_returns_float32_array(embedder):
    result = embedder.embed(["review one", "review two"])
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (2, 2)


def test_embed_default_model_name(embedder):
    assert "MiniLM" in embedder.model_name
