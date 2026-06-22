"""Tests for steamtools.review_topics.pipeline."""

from datetime import UTC
from unittest.mock import MagicMock

import numpy as np

from steamtools.db.connection import get_connection
from steamtools.db.store import StoDB
from steamtools.review_topics.pipeline import ReviewTopicPipeline


def _now_iso():
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _insert_reviews(appid: int, texts: list[str]) -> list[str]:
    ids = [f"r{i}" for i in range(len(texts))]
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, "Test", _now_iso()),
        )
        for rid, text in zip(ids, texts):
            conn.execute(
                "INSERT OR IGNORE INTO app_reviews (review_id, appid, review, fetched_at) VALUES (?, ?, ?, ?)",
                (rid, appid, text, _now_iso()),
            )
    return ids


def _make_pipeline(mocker, vectors: np.ndarray | None = None, cluster_result: dict | None = None):
    db = StoDB()
    vm = MagicMock()
    embedder = MagicMock()
    embedder.model_name = "test-model"
    n = len(vectors) if vectors is not None else 2
    embedder.embed.return_value = vectors if vectors is not None else np.zeros((n, 4), dtype=np.float32)

    clusterer = MagicMock()
    default_labels = np.array([0] * n)
    default_centroids = {0: np.zeros(4, dtype=np.float32)}
    clusterer.fit.return_value = cluster_result or {
        "labels": default_labels,
        "centroids": default_centroids,
        "noise_count": 0,
    }

    labeler = MagicMock()
    labeler.model_name = "llm-model"
    labeler.label_cluster.return_value = {"category_name": "Fun", "description": "Players enjoyed the game."}

    return ReviewTopicPipeline(db, vm, embedder, clusterer, labeler), db


# ── run_discovery ─────────────────────────────────────────────────────────────


def test_run_discovery_no_reviews(mocker):
    pipeline, _ = _make_pipeline(mocker)
    result = pipeline.run_discovery(appid=9999)
    assert "error" in result


def test_run_discovery_success(mocker):
    texts = [" ".join(["word"] * 15) for _ in range(3)]
    _insert_reviews(1, texts)
    vecs = np.eye(3, 4, dtype=np.float32)
    pipeline, db = _make_pipeline(
        mocker,
        vectors=vecs,
        cluster_result={
            "labels": np.array([0, 0, -1]),
            "centroids": {0: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)},
            "noise_count": 1,
        },
    )
    result = pipeline.run_discovery(appid=1)
    assert "run_id" in result
    assert result["clusters_found"] == 1
    assert result["noise_count"] == 1
    assert len(result["topics"]) == 1


# ── classify_reviews ──────────────────────────────────────────────────────────


def test_classify_reviews_no_topics(mocker):
    _insert_reviews(1, ["review one two three four five six seven eight nine ten"])
    pipeline, db = _make_pipeline(mocker)
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    result = pipeline.classify_reviews(1, run_id)
    assert "error" in result


def test_classify_reviews_no_centroid_vectors(mocker):
    _insert_reviews(1, ["review one two three four five six seven eight nine ten"])
    pipeline, db = _make_pipeline(mocker)
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    db.save_topics(
        run_id,
        1,
        [
            {
                "cluster_label": 0,
                "category_name": "T",
                "description": "D",
                "review_count": 1,
                "sample_review_ids": [],
                "centroid_vector": None,
            },
        ],
    )
    result = pipeline.classify_reviews(1, run_id)
    assert "error" in result


def test_classify_reviews_no_reviews_returns_zeros(mocker):
    pipeline, db = _make_pipeline(mocker)
    run_id = db.create_topic_run(2, "m", "l", {}, "c")
    db.save_topics(
        run_id,
        2,
        [
            {
                "cluster_label": 0,
                "category_name": "T",
                "description": "D",
                "review_count": 1,
                "sample_review_ids": [],
                "centroid_vector": [1.0, 0.0, 0.0, 0.0],
            },
        ],
    )
    result = pipeline.classify_reviews(2, run_id)
    assert result == {"assigned": 0, "uncategorized": 0}


def test_classify_reviews_assigns_and_noise(mocker):
    texts = [" ".join(["word"] * 15) for _ in range(2)]
    _insert_reviews(3, texts)
    # High-similarity vector → assigned; low → noise
    vecs = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    pipeline, db = _make_pipeline(mocker, vectors=vecs)
    pipeline._embedder.embed.return_value = vecs

    run_id = db.create_topic_run(3, "m", "l", {}, "c")
    db.save_topics(
        run_id,
        3,
        [
            {
                "cluster_label": 0,
                "category_name": "T",
                "description": "D",
                "review_count": 2,
                "sample_review_ids": [],
                "centroid_vector": [1.0, 0.0, 0.0, 0.0],
            },
        ],
    )
    result = pipeline.classify_reviews(3, run_id, threshold=0.9)
    assert result["assigned"] + result["uncategorized"] == 2
