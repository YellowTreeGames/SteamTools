import numpy as np
from sklearn.cluster import HDBSCAN


class ReviewClusterer:
    def __init__(self, min_cluster_size: int = 15):
        self.min_cluster_size = min_cluster_size

    def fit(self, vectors: np.ndarray) -> dict:
        """Run HDBSCAN and return labels, per-cluster centroids, and noise count."""
        clusterer = HDBSCAN(min_cluster_size=self.min_cluster_size)
        labels = clusterer.fit_predict(vectors)

        unique_labels = set(labels)
        unique_labels.discard(-1)

        centroids = {}
        for label in unique_labels:
            mask = labels == label
            centroids[int(label)] = vectors[mask].mean(axis=0)

        noise_count = int((labels == -1).sum())
        return {"labels": labels, "centroids": centroids, "noise_count": noise_count}
