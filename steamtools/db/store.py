"""StoDB — central database API for SteamTools.

All callers (CLI, MCP) go through this class rather than opening their own
connections or writing raw SQL.
"""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime

from steamtools.db.connection import get_connection, init_db
from steamtools.db.staleness import needs_refresh_details, needs_refresh_review_summary
from steamtools.steam_client import (
    get_app_details as _steam_app_details,
)
from steamtools.steam_client import (
    get_app_list as _steam_app_list,
)
from steamtools.steam_client import (
    get_app_list_page as _steam_app_list_page,
)
from steamtools.steam_client import (
    get_app_reviews as _steam_app_reviews,
)

DEFAULT_DETAILS_SLEEP: float = 1.5


class StoDB:
    def __init__(self, details_sleep: float = DEFAULT_DETAILS_SLEEP):
        self._details_sleep = details_sleep
        init_db()

    # ── Apps ──────────────────────────────────────────────────────────────────

    def search_apps(self, query: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT apps.appid, apps.name,
                       (app_details.appid IS NOT NULL) AS has_details
                FROM apps
                LEFT JOIN app_details ON app_details.appid = apps.appid
                WHERE apps.name LIKE ? COLLATE NOCASE
                ORDER BY apps.name
                """,
                (f"%{query}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def app_stats(self) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(app_details.appid) AS with_details,
                       MAX(apps.last_seen_at) AS last_fetched
                FROM apps
                LEFT JOIN app_details ON app_details.appid = apps.appid
                """
            ).fetchone()
        return dict(row)

    def app_details_stats(self) -> dict:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total, MAX(fetched_at) AS last_fetched FROM app_details").fetchone()
        return dict(row)

    def status(self) -> dict:
        """Combined status from both tables."""
        apps = self.app_stats()
        details = self.app_details_stats()
        return {
            "apps_total": apps["total"],
            "apps_with_details": apps["with_details"],
            "apps_missing_details": apps["total"] - apps["with_details"],
            "apps_last_fetched": apps["last_fetched"],
            "details_total": details["total"],
            "details_last_fetched": details["last_fetched"],
        }

    def sync_app_list(self, count: int | None = None) -> int:
        """Upsert the apps table from Steam's GetAppList endpoint.

        count=None does a full catalog refresh; count=N fetches one page of
        that size starting from the latest appid we already have.
        Returns the number of apps upserted.
        """
        if count is None:
            apps = _steam_app_list()
        else:
            with get_connection() as conn:
                last = conn.execute("SELECT MAX(appid) AS m FROM apps").fetchone()["m"] or 0
            apps = _steam_app_list_page(last_appid=last, max_results=count)["apps"]

        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO apps (appid, name, last_seen_at)
                VALUES (:appid, :name, :last_seen_at)
                ON CONFLICT(appid) DO UPDATE SET
                    name = excluded.name,
                    last_seen_at = excluded.last_seen_at
                """,
                [{"appid": a["appid"], "name": a["name"], "last_seen_at": now} for a in apps],
            )
        return len(apps)

    # ── App Details ───────────────────────────────────────────────────────────

    def get_app_details(self, appids: list[int]) -> dict[int, dict | None]:
        """Return app_details rows keyed by appid, fetching from Steam if stale or missing.

        Value is None for appids confirmed not to be games.
        """
        existing = self._fetch_details_rows(appids)
        stale = [aid for aid in appids if needs_refresh_details(existing.get(aid))]
        for appid in stale:
            self.sync_app_details_one(appid, force=True)
        if stale:
            existing = self._fetch_details_rows(appids)
        return {aid: existing.get(aid) for aid in appids}

    def sync_app_details(
        self,
        limit: int | None = None,
        on_progress: Callable[[int, int, int, dict], None] | None = None,
    ) -> int:
        """Fetch details for all apps that are missing or stale (>30 days).

        Returns the number of appids processed.
        """
        with get_connection() as conn:
            query = """
                SELECT apps.appid FROM apps
                LEFT JOIN app_details ON app_details.appid = apps.appid
                WHERE app_details.appid IS NULL
                   OR app_details.fetched_at < datetime('now', '-30 days')
                ORDER BY apps.appid
            """
            if limit is not None:
                query += f" LIMIT {limit}"
            rows = conn.execute(query).fetchall()
        appids = [r["appid"] for r in rows]

        for i, appid in enumerate(appids, start=1):
            result = self.sync_app_details_one(appid, force=True)
            if on_progress:
                on_progress(i, len(appids), appid, result)

        return len(appids)

    def sync_app_details_one(self, appid: int, force: bool = False) -> dict:
        """Fetch and upsert details for a single appid.

        Returns {"status": "game"|"not_a_game"|"already_current",
                 "appid": int, "row": dict|None, "detected_type": str|None}.
        """
        existing = self._fetch_details_rows([appid])
        if not force and appid in existing and not needs_refresh_details(existing[appid]):
            return {"status": "already_current", "appid": appid, "row": existing[appid], "detected_type": None}

        data = _steam_app_details(appid)
        time.sleep(self._details_sleep)

        with get_connection() as conn:
            if data is not None and data.get("type") == "game":
                row = self._row_from_details(appid, data)
                conn.execute(
                    f"INSERT OR REPLACE INTO app_details ({', '.join(row)}) VALUES ({', '.join(f':{k}' for k in row)})",
                    row,
                )
                return {"status": "game", "appid": appid, "row": row, "detected_type": "game"}
            else:
                conn.execute("DELETE FROM apps WHERE appid = ?", (appid,))
                return {
                    "status": "not_a_game",
                    "appid": appid,
                    "row": None,
                    "detected_type": data.get("type") if data else None,
                }

    # ── Reviews ───────────────────────────────────────────────────────────────

    def sync_reviews(self, appid: int, force: bool = False, language: str = "all") -> dict:
        """Fetch and upsert all reviews for an appid from Steam.

        Paginates until the cursor stops advancing. Individual review rows are
        immutable once written — new pages only append, they never delete.

        Returns {"status": "fetched"|"already_current", "summary": dict|None,
                 "reviews_fetched": int}.
        """
        existing = self._fetch_review_summary(appid)
        if not force and not needs_refresh_review_summary(existing):
            return {"status": "already_current", "summary": existing, "reviews_fetched": 0}

        cursor = "*"
        total_fetched = 0
        query_summary: dict | None = None
        now = datetime.now(UTC).isoformat()

        while True:
            page = _steam_app_reviews(appid, cursor=cursor, language=language, filter="recent")
            if not page.get("success"):
                break
            if query_summary is None:
                query_summary = page.get("query_summary") or {}
            reviews = page.get("reviews") or []
            if not reviews:
                break
            with get_connection() as conn:
                conn.executemany(
                    f"""INSERT OR REPLACE INTO app_reviews
                        ({", ".join(self._review_columns())})
                        VALUES ({", ".join(f":{c}" for c in self._review_columns())})""",
                    [self._row_from_review(appid, r, now) for r in reviews],
                )
            total_fetched += len(reviews)
            new_cursor = page.get("cursor", "")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor

        if query_summary is not None:
            with get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO app_review_summary
                       (appid, total_reviews, total_positive, total_negative,
                        review_score, review_score_desc, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        appid,
                        query_summary.get("total_reviews"),
                        query_summary.get("total_positive"),
                        query_summary.get("total_negative"),
                        query_summary.get("review_score"),
                        query_summary.get("review_score_desc"),
                        now,
                    ),
                )

        return {"status": "fetched", "summary": query_summary, "reviews_fetched": total_fetched}

    def get_review_summary(self, appid: int) -> dict | None:
        """Return review summary for appid, fetching from Steam if stale or missing."""
        row = self._fetch_review_summary(appid)
        if needs_refresh_review_summary(row):
            result = self.sync_reviews(appid)
            return result["summary"]
        return row

    def review_stats(self) -> dict:
        with get_connection() as conn:
            s = conn.execute("SELECT COUNT(*) AS games, MAX(fetched_at) AS last_fetched FROM app_review_summary").fetchone()
            r = conn.execute("SELECT COUNT(*) AS total FROM app_reviews").fetchone()
        return {
            "games_with_reviews": s["games"],
            "total_reviews": r["total"],
            "last_fetched": s["last_fetched"],
        }

    def _fetch_review_summary(self, appid: int) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM app_review_summary WHERE appid = ?", (appid,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _review_columns() -> list[str]:
        return [
            "recommendationid",
            "appid",
            "author_steamid",
            "author_num_games_owned",
            "author_num_reviews",
            "author_playtime_forever",
            "author_playtime_at_review",
            "language",
            "review",
            "timestamp_created",
            "timestamp_updated",
            "voted_up",
            "votes_up",
            "votes_funny",
            "weighted_vote_score",
            "comment_count",
            "steam_purchase",
            "received_for_free",
            "written_during_early_access",
            "fetched_at",
        ]

    @staticmethod
    def _row_from_review(appid: int, review: dict, fetched_at: str) -> dict:
        author = review.get("author") or {}
        return {
            "recommendationid": int(review["recommendationid"]),
            "appid": appid,
            "author_steamid": author.get("steamid"),
            "author_num_games_owned": author.get("num_games_owned"),
            "author_num_reviews": author.get("num_reviews"),
            "author_playtime_forever": author.get("playtime_forever"),
            "author_playtime_at_review": author.get("playtime_at_review"),
            "language": review.get("language"),
            "review": review.get("review"),
            "timestamp_created": review.get("timestamp_created"),
            "timestamp_updated": review.get("timestamp_updated"),
            "voted_up": int(bool(review.get("voted_up"))),
            "votes_up": review.get("votes_up"),
            "votes_funny": review.get("votes_funny"),
            "weighted_vote_score": float(review.get("weighted_vote_score") or 0),
            "comment_count": review.get("comment_count"),
            "steam_purchase": int(bool(review.get("steam_purchase"))),
            "received_for_free": int(bool(review.get("received_for_free"))),
            "written_during_early_access": int(bool(review.get("written_during_early_access"))),
            "fetched_at": fetched_at,
        }

    def _fetch_rows(self, table: str, appids: list[int]) -> dict[int, dict]:
        if not appids:
            return {}
        ph = ",".join("?" * len(appids))
        with get_connection() as conn:
            rows = conn.execute(f"SELECT * FROM {table} WHERE appid IN ({ph})", appids).fetchall()  # noqa: S608
        return {r["appid"]: dict(r) for r in rows}

    def _fetch_details_rows(self, appids: list[int]) -> dict[int, dict]:
        return self._fetch_rows("app_details", appids)

    @staticmethod
    def _row_from_details(appid: int, data: dict) -> dict:
        price = data.get("price_overview") or {}
        release = data.get("release_date") or {}
        platforms = data.get("platforms") or {}
        return {
            "appid": appid,
            "type": data.get("type"),
            "name": data.get("name"),
            "required_age": data.get("required_age") or None,
            "is_free": int(bool(data.get("is_free"))),
            "short_description": data.get("short_description"),
            "detailed_description": data.get("detailed_description"),
            "about_the_game": data.get("about_the_game"),
            "supported_languages": data.get("supported_languages"),
            "header_image": data.get("header_image"),
            "website": data.get("website"),
            "release_date": release.get("date"),
            "coming_soon": int(bool(release.get("coming_soon"))),
            "developers": json.dumps(data.get("developers") or []),
            "publishers": json.dumps(data.get("publishers") or []),
            "genres": json.dumps([g["description"] for g in data.get("genres") or []]),
            "categories": json.dumps([c["description"] for c in data.get("categories") or []]),
            "platforms_windows": int(bool(platforms.get("windows"))),
            "platforms_mac": int(bool(platforms.get("mac"))),
            "platforms_linux": int(bool(platforms.get("linux"))),
            "price_currency": price.get("currency"),
            "price_initial": price.get("initial"),
            "price_final": price.get("final"),
            "price_discount_percent": price.get("discount_percent"),
            "metacritic_score": (data.get("metacritic") or {}).get("score"),
            "achievements_total": (data.get("achievements") or {}).get("total"),
            "dlc": json.dumps(data.get("dlc") or []),
            "screenshots": json.dumps(data.get("screenshots") or []),
            "movies": json.dumps(data.get("movies") or []),
            "content_descriptors": json.dumps(data.get("content_descriptors") or {}),
            "background": data.get("background"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
