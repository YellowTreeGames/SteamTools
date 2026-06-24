"""AnalysisDB — pure DB layer for analysis results. No pipeline logic, no Steam imports."""

from datetime import UTC, datetime

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
