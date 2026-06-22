"""Tests for steamtools.review_topics.clusterer."""

import numpy as np

from steamtools.review_topics.clusterer import ReviewClusterer


def _vecs(n: int, dims: int = 4) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.random((n, dims)).astype(np.float32)


def test_fit_returns_required_keys():
    clusterer = ReviewClusterer(min_cluster_size=2)
    result = clusterer.fit(_vecs(20))
    assert "labels" in result
    assert "centroids" in result
    assert "noise_count" in result


def test_fit_labels_length_matches_input():
    vecs = _vecs(30)
    clusterer = ReviewClusterer(min_cluster_size=2)
    result = clusterer.fit(vecs)
    assert len(result["labels"]) == 30


def test_fit_noise_count_is_non_negative():
    clusterer = ReviewClusterer(min_cluster_size=2)
    result = clusterer.fit(_vecs(20))
    assert result["noise_count"] >= 0


def test_fit_centroids_exclude_noise_label():
    clusterer = ReviewClusterer(min_cluster_size=2)
    result = clusterer.fit(_vecs(20))
    assert -1 not in result["centroids"]


def test_fit_centroid_shape_matches_vector_dims():
    vecs = _vecs(20, dims=8)
    clusterer = ReviewClusterer(min_cluster_size=2)
    result = clusterer.fit(vecs)
    for centroid in result["centroids"].values():
        assert centroid.shape == (8,)


def test_fit_all_noise_when_min_cluster_too_large():
    vecs = _vecs(5, dims=4)
    clusterer = ReviewClusterer(min_cluster_size=100)
    result = clusterer.fit(vecs)
    assert result["noise_count"] == 5
    assert result["centroids"] == {}
