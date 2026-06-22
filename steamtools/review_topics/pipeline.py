"""End-to-end review topic discovery and classification pipeline."""

import json
from datetime import datetime, timezone

import numpy as np

from steamtools.db.store import StoDB
from steamtools.vectordb.manager import VectorManager
from steamtools.review_topics.embedder import ReviewEmbedder
from steamtools.review_topics.clusterer import ReviewClusterer
from steamtools.review_topics.labeler import ClusterLabeler


class ReviewTopicPipeline:
    def __init__(
        self,
        db: StoDB,
        vm: VectorManager,
        embedder: ReviewEmbedder,
        clusterer: ReviewClusterer,
        labeler: ClusterLabeler,
    ):
        self._db = db
        self._vm = vm
        self._embedder = embedder
        self._clusterer = clusterer
        self._labeler = labeler

    def run_discovery(self, appid: int, min_cluster_size: int = 15) -> dict:
        """Embed reviews, cluster, label, and persist topics. Returns run summary."""
        reviews = self._db.get_reviews(appid)
        if not reviews:
            return {"error": "No reviews found for this appid. Run fetch-text first."}

        texts = [r["review"] for r in reviews]
        review_ids = [r["review_id"] for r in reviews]

        vectors = self._embedder.embed(texts)

        collection_name = f"reviews_{appid}"
        self._vm.upsert(
            collection_name,
            ids=review_ids,
            documents=texts,
            metadatas=[{"appid": appid} for _ in reviews],
            embeddings=vectors.tolist(),
        )

        hdbscan_params = {"min_cluster_size": min_cluster_size}
        run_id = self._db.create_topic_run(
            appid=appid,
            embedding_model=self._embedder.model_name,
            llm_model=self._labeler.model_name,
            hdbscan_params=hdbscan_params,
            chroma_collection=collection_name,
        )

        self._db.update_topic_run(run_id, reviews_embedded=len(texts))

        cluster_result = ReviewClusterer(min_cluster_size=min_cluster_size).fit(vectors)
        labels = cluster_result["labels"]
        centroids = cluster_result["centroids"]
        noise_count = cluster_result["noise_count"]

        id_array = np.array(review_ids)
        topics_data = []
        for label, centroid in centroids.items():
            member_mask = labels == label
            member_ids = id_array[member_mask].tolist()
            member_vectors = vectors[member_mask]

            # Find 10 nearest reviews to the centroid by Euclidean distance
            dists = np.linalg.norm(member_vectors - centroid, axis=1)
            nearest_idx = np.argsort(dists)[:10]
            sample_ids = [member_ids[i] for i in nearest_idx]

            id_to_text = {r["review_id"]: r["review"] for r in reviews}
            sample_texts = [id_to_text[sid] for sid in sample_ids if sid in id_to_text]

            label_result = self._labeler.label_cluster(sample_texts)

            topics_data.append({
                "cluster_label": label,
                "category_name": label_result["category_name"],
                "description": label_result["description"],
                "review_count": int(member_mask.sum()),
                "sample_review_ids": sample_ids,
                "centroid_vector": centroid.tolist(),
            })

        topic_ids = self._db.save_topics(run_id, appid, topics_data)

        label_to_topic_id = {
            t["cluster_label"]: topic_ids[i] for i, t in enumerate(topics_data)
        }
        assignments = []
        for i, label in enumerate(labels):
            is_noise = int(label == -1)
            assignments.append({
                "review_id": review_ids[i],
                "topic_id": label_to_topic_id.get(int(label)) if not is_noise else None,
                "similarity_score": None,
                "is_noise": is_noise,
            })
        self._db.save_topic_assignments(run_id, assignments)

        completed_at = datetime.now(timezone.utc).isoformat()
        self._db.update_topic_run(
            run_id,
            status="complete",
            clusters_found=len(centroids),
            noise_count=noise_count,
            completed_at=completed_at,
        )

        return {
            "run_id": run_id,
            "clusters_found": len(centroids),
            "noise_count": noise_count,
            "topics": [
                {"category_name": t["category_name"], "review_count": t["review_count"]}
                for t in topics_data
            ],
        }

    def classify_reviews(
        self, appid: int, run_id: int, threshold: float = 0.85
    ) -> dict:
        """Assign unclassified reviews to topics by cosine similarity to stored centroids."""
        topics = self._db.get_topics(run_id)
        if not topics:
            return {"error": "No topics found for this run."}

        centroids = {}
        for t in topics:
            if t["centroid_vector"]:
                centroids[t["id"]] = np.array(json.loads(t["centroid_vector"]), dtype=np.float32)

        if not centroids:
            return {"error": "No centroid vectors stored for this run."}

        centroid_ids = list(centroids.keys())
        centroid_matrix = np.stack([centroids[tid] for tid in centroid_ids])

        centroid_norms = np.linalg.norm(centroid_matrix, axis=1, keepdims=True)
        centroid_matrix_norm = centroid_matrix / np.where(centroid_norms == 0, 1, centroid_norms)

        reviews = self._db.get_reviews(appid)
        if not reviews:
            return {"assigned": 0, "uncategorized": 0}

        texts = [r["review"] for r in reviews]
        review_ids = [r["review_id"] for r in reviews]
        vectors = self._embedder.embed(texts)

        assignments = []
        assigned = 0
        uncategorized = 0

        for i, vec in enumerate(vectors):
            vec_norm = vec / (np.linalg.norm(vec) or 1.0)
            sims = centroid_matrix_norm @ vec_norm
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])

            if best_sim >= threshold:
                assignments.append({
                    "review_id": review_ids[i],
                    "topic_id": centroid_ids[best_idx],
                    "similarity_score": best_sim,
                    "is_noise": 0,
                })
                assigned += 1
            else:
                assignments.append({
                    "review_id": review_ids[i],
                    "topic_id": None,
                    "similarity_score": best_sim,
                    "is_noise": 1,
                })
                uncategorized += 1

        self._db.save_topic_assignments(run_id, assignments)
        return {"assigned": assigned, "uncategorized": uncategorized}
