"""AnalysisDB — pure DB layer for analysis results. No pipeline logic, no Steam imports."""

import json
from datetime import UTC, datetime
from typing import cast

from steamtools.analysis.connection import get_connection, init_db


class AnalysisDB:
    def __init__(self) -> None:
        init_db()

    def get_processed_review_ids(self, appid: int) -> set[int]:
        with get_connection() as conn:
            rows = conn.execute("SELECT review_id FROM absa_processed WHERE appid = ?", (appid,)).fetchall()
        return {r["review_id"] for r in rows}

    def save_absa_result(self, review_id: int, appid: int, aspects: list[dict], model: str) -> None:
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO absa_processed (review_id, appid, analyzed_at, model) VALUES (?, ?, ?, ?)",
                (review_id, appid, now, model),
            )
            conn.executemany(
                """
                INSERT INTO absa_aspects (review_id, appid, category, specific_feature, sentiment, rationale)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(review_id, appid, a["category"], a["specific_feature"], a["sentiment"], a["rationale"]) for a in aspects],
            )

    def delete_absa_result(self, review_id: int, appid: int) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM absa_processed WHERE review_id = ? AND appid = ?", (review_id, appid))
            conn.execute("DELETE FROM absa_aspects WHERE review_id = ? AND appid = ?", (review_id, appid))

    def wipe_game_absa(self, appid: int) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM absa_taxonomy_features WHERE appid = ?", (appid,))
            conn.execute("DELETE FROM absa_taxonomy_categories WHERE appid = ?", (appid,))
            conn.execute("DELETE FROM absa_taxonomy WHERE appid = ?", (appid,))
            conn.execute("DELETE FROM absa_processed WHERE appid = ?", (appid,))
            conn.execute("DELETE FROM absa_aspects WHERE appid = ?", (appid,))

    def get_taxonomy(self, appid: int) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM absa_taxonomy WHERE appid = ?", (appid,)).fetchone()
        return dict(row) if row else None

    def upsert_taxonomy(self, appid: int, status: str, discovery_sample_size: int, model: str) -> None:
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO absa_taxonomy (appid, status, discovery_sample_size, model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (appid, status, discovery_sample_size, model, now, now),
            )

    def save_taxonomy_data(
        self,
        appid: int,
        categories: list[dict],
        *,
        discovery_sample_size: int,
        discovery_reviews_sampled: int,
        early_stopped: bool,
        model: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO absa_taxonomy
                    (appid, status, discovery_sample_size, discovery_reviews_sampled,
                     early_stopped, model, created_at, updated_at)
                VALUES (?, 'ready', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    status = 'ready',
                    discovery_reviews_sampled = excluded.discovery_reviews_sampled,
                    early_stopped = excluded.early_stopped,
                    updated_at = excluded.updated_at
                """,
                (appid, discovery_sample_size, discovery_reviews_sampled, int(early_stopped), model, now, now),
            )
            for cat in categories:
                conn.execute(
                    "INSERT OR IGNORE INTO absa_taxonomy_categories (appid, name, is_seed) VALUES (?, ?, ?)",
                    (appid, cat["name"], int(cat["is_seed"])),
                )
                cat_row = conn.execute(
                    "SELECT id FROM absa_taxonomy_categories WHERE appid = ? AND name = ?",
                    (appid, cat["name"]),
                ).fetchone()
                cat_id = cat_row["id"]
                for feat in cat["features"]:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO absa_taxonomy_features (appid, category_id, canonical_name, aliases)
                        VALUES (?, ?, ?, ?)
                        """,
                        (appid, cat_id, feat["canonical_name"], json.dumps(feat["aliases"])),
                    )

    def extend_taxonomy(self, appid: int, new_pairs: list[tuple[str, str]]) -> None:
        """Add new (category, feature) pairs to the taxonomy. Creates the category row if needed."""
        with get_connection() as conn:
            for category, feature in new_pairs:
                conn.execute(
                    "INSERT OR IGNORE INTO absa_taxonomy_categories (appid, name, is_seed) VALUES (?, ?, 0)",
                    (appid, category),
                )
                cat_row = conn.execute(
                    "SELECT id FROM absa_taxonomy_categories WHERE appid = ? AND name = ?",
                    (appid, category),
                ).fetchone()
                cat_id = cat_row["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO absa_taxonomy_features (appid, category_id, canonical_name, aliases)"
                    " VALUES (?, ?, ?, '[]')",
                    (appid, cat_id, feature),
                )

    def get_taxonomy_for_classify(self, appid: int) -> dict[str, list[str]]:
        with get_connection() as conn:
            cats = conn.execute(
                "SELECT id, name FROM absa_taxonomy_categories WHERE appid = ? ORDER BY name",
                (appid,),
            ).fetchall()
            result: dict[str, list[str]] = {}
            for cat in cats:
                feats = conn.execute(
                    "SELECT canonical_name FROM absa_taxonomy_features"
                    " WHERE appid = ? AND category_id = ? ORDER BY canonical_name",
                    (appid, cat["id"]),
                ).fetchall()
                result[cat["name"]] = [f["canonical_name"] for f in feats]
        return result

    def get_absa_aspects(self, appid: int, category: str | None = None, sentiment: str | None = None) -> list[dict]:
        query = "SELECT * FROM absa_aspects WHERE appid = ?"
        params: list[object] = [appid]
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if sentiment is not None:
            query += " AND sentiment = ?"
            params.append(sentiment)
        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_feature_breakdown(self, appid: int) -> list[dict]:
        """Return per-category feature breakdown with sentiment counts, sorted by total mentions."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT category, specific_feature, LOWER(sentiment) as sentiment, COUNT(*) as count
                FROM absa_aspects
                WHERE appid = ?
                GROUP BY category, specific_feature, LOWER(sentiment)
                """,
                (appid,),
            ).fetchall()

        # Aggregate into {category: {feature: {sentiment: count}}}
        cats: dict[str, dict[str, dict[str, int]]] = {}
        for r in rows:
            cats.setdefault(r["category"], {}).setdefault(r["specific_feature"], {})[r["sentiment"]] = r["count"]

        result = []
        for cat, features in cats.items():
            cat_total = sum(sum(s.values()) for s in features.values())
            feat_list = []
            for feat, sentiments in features.items():
                pos = sentiments.get("positive", 0)
                neg = sentiments.get("negative", 0)
                feat_list.append(
                    {
                        "feature": feat,
                        "positive": pos,
                        "negative": neg,
                        "mixed": sentiments.get("mixed", 0),
                        "total": sum(sentiments.values()),
                        "score": pos - neg,
                    }
                )
            feat_list.sort(key=lambda f: cast(int, f["score"]), reverse=True)
            cat_score = sum(cast(int, f["score"]) for f in feat_list)
            result.append({"category": cat, "total": cat_total, "score": cat_score, "features": feat_list})

        result.sort(key=lambda c: cast(int, c["total"]), reverse=True)
        return result

    def absa_stats(self, appid: int) -> dict:
        with get_connection() as conn:
            by_category = conn.execute(
                "SELECT category, COUNT(*) as count FROM absa_aspects WHERE appid = ? GROUP BY category ORDER BY count DESC",
                (appid,),
            ).fetchall()
            by_sentiment = conn.execute(
                "SELECT sentiment, COUNT(*) as count FROM absa_aspects WHERE appid = ? GROUP BY sentiment ORDER BY count DESC",
                (appid,),
            ).fetchall()
            total_processed = conn.execute("SELECT COUNT(*) FROM absa_processed WHERE appid = ?", (appid,)).fetchone()[0]
        return {
            "appid": appid,
            "reviews_processed": total_processed,
            "by_category": [dict(r) for r in by_category],
            "by_sentiment": [dict(r) for r in by_sentiment],
        }
