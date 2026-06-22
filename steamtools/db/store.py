"""StoDB — central database API for SteamTools.

All callers (CLI, apps, processes) go through this class rather than opening
their own connections or writing raw SQL.  Methods that can return stale data
check staleness and dispatch to internal sync helpers before returning when
auto_sync=True (the default).
"""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime

from steamtools.db.connection import get_connection, init_db
from steamtools.db.staleness import needs_refresh_details, needs_refresh_reviews
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
    get_review_counts as _steam_review_counts,
)
from steamtools.steam_client import (
    get_reviews_page as _steam_reviews_page,
)

DEFAULT_DETAILS_SLEEP: float = 1.5
DEFAULT_REVIEWS_SLEEP: float = 1.0


def _upsert_review_count(conn, appid: int, data: dict, now: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO app_review_counts "
        "(appid, total_reviews, total_positive, total_negative, review_score, review_score_desc, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            appid,
            data["total_reviews"],
            data["total_positive"],
            data["total_negative"],
            data["review_score"],
            data["review_score_desc"],
            now,
        ),
    )


def _filter_stale_review_rows(rows) -> list[int]:
    return [
        r["appid"]
        for r in rows
        if needs_refresh_reviews(
            {"fetched_at": r["fetched_at"]} if r["fetched_at"] else None,
            {"coming_soon": r["coming_soon"], "release_date": r["release_date"]},
        )
    ]


class StoDB:
    def __init__(
        self,
        details_sleep: float = DEFAULT_DETAILS_SLEEP,
        reviews_sleep: float = DEFAULT_REVIEWS_SLEEP,
    ):
        self._details_sleep = details_sleep
        self._reviews_sleep = reviews_sleep
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
            row = conn.execute(
                "SELECT COUNT(*) AS total, MAX(appid) AS last_appid, MAX(fetched_at) AS last_fetched FROM app_details"
            ).fetchone()
        return dict(row)

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

    def get_app_details(self, appids: list[int], auto_sync: bool = True) -> dict[int, dict | None]:
        """Return app_details rows keyed by appid.

        With auto_sync=True, stale or missing rows are fetched from Steam
        before returning.  Value is None for appids confirmed not to be games.
        """
        existing = self._fetch_details_rows(appids)
        if auto_sync:
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

        on_progress(i, total, appid, result) is called after each appid.
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
        Short-circuits without a network call if the row exists and is current
        unless force=True.
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

    # ── Review Counts ─────────────────────────────────────────────────────────

    def get_review_counts(self, appids: list[int], auto_sync: bool = True) -> dict[int, dict | None]:
        """Return app_review_counts rows keyed by appid.

        With auto_sync=True, applies the staleness policy and fetches from
        Steam for any stale or missing rows before returning.
        Policy: monthly for unreleased/recently released games, yearly for
        games released over a year ago.
        """
        details_map = self._fetch_details_rows(appids)
        existing = self._fetch_review_rows(appids)
        if auto_sync:
            stale = [aid for aid in appids if needs_refresh_reviews(existing.get(aid), details_map.get(aid))]
            if stale:
                self.sync_review_counts(appids=stale)
                existing = self._fetch_review_rows(appids)
        return {aid: existing.get(aid) for aid in appids}

    def sync_review_counts(
        self,
        appids: list[int] | None = None,
        limit: int | None = None,
        on_progress: Callable[[int, int, int, dict | None], None] | None = None,
    ) -> int:
        """Fetch review counts for all stale or missing rows.

        If appids is given, only those are checked against the staleness policy;
        otherwise all games in app_details are candidates.
        Returns the number of appids that were actually synced (had data).
        """
        candidates = self._stale_review_candidates(appids)
        if limit is not None:
            candidates = candidates[:limit]

        now = datetime.now(UTC).isoformat()
        synced = 0
        for i, appid in enumerate(candidates, start=1):
            data = _steam_review_counts(appid)
            time.sleep(self._reviews_sleep)
            if data is not None:
                with get_connection() as conn:
                    _upsert_review_count(conn, appid, data, now)
                synced += 1
            if on_progress:
                on_progress(i, len(candidates), appid, data)

        return synced

    def get_stale_review_appids_for_evals(self) -> list[int]:
        """Appids that have eval_results but stale or missing review counts."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT er.appid,
                       ad.coming_soon, ad.release_date,
                       arc.fetched_at
                FROM eval_results er
                LEFT JOIN app_details ad ON ad.appid = er.appid
                LEFT JOIN app_review_counts arc ON arc.appid = er.appid
                """
            ).fetchall()
        return _filter_stale_review_rows(rows)

    def _stale_review_candidates(self, appids: list[int] | None) -> list[int]:
        if appids is not None:
            details_map = self._fetch_details_rows(appids)
            review_map = self._fetch_review_rows(appids)
            return [aid for aid in appids if needs_refresh_reviews(review_map.get(aid), details_map.get(aid))]
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT ad.appid, ad.coming_soon, ad.release_date, arc.fetched_at
                FROM app_details ad
                LEFT JOIN app_review_counts arc ON arc.appid = ad.appid
                """
            ).fetchall()
        return _filter_stale_review_rows(rows)

    def review_stats(self) -> dict:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total, MAX(fetched_at) AS last_fetched FROM app_review_counts").fetchone()
        return dict(row)

    def get_game_view(self, appid: int) -> dict | None:
        """Combined read-only view of apps + app_details + app_review_counts for one appid."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT apps.appid, apps.name, apps.last_seen_at,
                       ad.type, ad.required_age, ad.is_free,
                       ad.short_description, ad.detailed_description, ad.about_the_game,
                       ad.supported_languages, ad.header_image, ad.website,
                       ad.release_date, ad.coming_soon,
                       ad.developers, ad.publishers, ad.genres, ad.categories,
                       ad.platforms_windows, ad.platforms_mac, ad.platforms_linux,
                       ad.price_currency, ad.price_initial, ad.price_final, ad.price_discount_percent,
                       ad.metacritic_score, ad.achievements_total,
                       ad.dlc, ad.screenshots, ad.movies, ad.content_descriptors, ad.background,
                       ad.fetched_at AS details_fetched_at,
                       arc.total_reviews, arc.total_positive, arc.total_negative,
                       arc.review_score, arc.review_score_desc, arc.fetched_at AS reviews_fetched_at
                FROM apps
                LEFT JOIN app_details ad ON ad.appid = apps.appid
                LEFT JOIN app_review_counts arc ON arc.appid = apps.appid
                WHERE apps.appid = ?
                """,
                (appid,),
            ).fetchone()
        return dict(row) if row else None

    def _fetch_review_rows(self, appids: list[int]) -> dict[int, dict]:
        return self._fetch_rows("app_review_counts", appids)

    # ── Evals ─────────────────────────────────────────────────────────────────

    def get_eval_type(self, name: str) -> dict:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM eval_types WHERE name = ?", (name,)).fetchone()
            if row is not None:
                return dict(row)
            available = [r["name"] for r in conn.execute("SELECT name FROM eval_types ORDER BY id").fetchall()]
        raise ValueError(f"Unknown eval type {name!r}. Available: {', '.join(available)}")

    def get_pending_eval_games(
        self,
        eval_type_id: int,
        appids: list[int],
        n: int | None = None,
        fill: bool = False,
        max_scores: int = 5,
        min_reviews: int = 1,
    ) -> list[dict]:
        with get_connection() as conn:
            if appids:
                ph = ",".join("?" * len(appids))
                rows = conn.execute(
                    f"""
                    SELECT ad.appid, ad.name, ad.short_description,
                           COALESCE(er.run_count, 0) AS run_count
                    FROM app_details ad
                    JOIN app_review_counts arc ON arc.appid = ad.appid
                    LEFT JOIN (
                        SELECT appid, COUNT(*) AS run_count
                        FROM eval_results WHERE eval_type = ? GROUP BY appid
                    ) er ON er.appid = ad.appid
                    WHERE ad.short_description IS NOT NULL AND ad.short_description != ''
                      AND ad.coming_soon = 0
                      AND arc.total_reviews >= ?
                      AND ad.appid IN ({ph})
                      AND COALESCE(er.run_count, 0) < ?
                    """,
                    (eval_type_id, min_reviews, *appids, max_scores),
                ).fetchall()
            else:
                limit_clause = f"LIMIT {n}" if n is not None else ""
                already_started = "AND er.run_count > 0" if fill else ""
                rows = conn.execute(
                    f"""
                    SELECT ad.appid, ad.name, ad.short_description,
                           COALESCE(er.run_count, 0) AS run_count
                    FROM app_details ad
                    JOIN app_review_counts arc ON arc.appid = ad.appid
                    LEFT JOIN (
                        SELECT appid, COUNT(*) AS run_count
                        FROM eval_results WHERE eval_type = ? GROUP BY appid
                    ) er ON er.appid = ad.appid
                    WHERE ad.short_description IS NOT NULL AND ad.short_description != ''
                      AND ad.coming_soon = 0
                      AND arc.total_reviews >= ?
                      AND COALESCE(er.run_count, 0) < ?
                      {already_started}
                    ORDER BY RANDOM()
                    {limit_clause}
                    """,
                    (eval_type_id, min_reviews, max_scores),
                ).fetchall()
        return [dict(r) for r in rows]

    def save_eval_result(
        self,
        appid: int,
        eval_type_id: int,
        score: float,
        rationale: str,
        model: str,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(eval_number), 0) + 1 AS next FROM eval_results WHERE appid = ? AND eval_type = ?",
                (appid, eval_type_id),
            ).fetchone()
            eval_number = row["next"]
            conn.execute(
                "INSERT INTO eval_results (appid, eval_type, eval_number, score, rationale, model, evaled_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (appid, eval_type_id, eval_number, score, rationale, model, now),
            )
        return eval_number

    def get_eval_correlation_data(self, eval_type_id: int) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT er.appid, AVG(er.score) AS avg_score, arc.total_reviews
                FROM eval_results er
                JOIN app_review_counts arc ON arc.appid = er.appid
                WHERE er.eval_type = ?
                GROUP BY er.appid
                """,
                (eval_type_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def has_app_details(self) -> bool:
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM app_details").fetchone()[0] > 0

    # ── Review Texts ──────────────────────────────────────────────────────────

    def _open_review_session(self, appid: int, filter_type: str, max_reviews: int) -> int:
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO review_fetch_sessions (appid, started_at, filter, max_reviews) VALUES (?, ?, ?, ?)",
                (appid, now, filter_type, max_reviews),
            )
            return cur.lastrowid

    def _paginate_reviews(
        self,
        appid: int,
        max_reviews: int,
        filter_type: str,
        sleep: float,
        on_progress: Callable[[int, int], None] | None,
    ) -> tuple[int, str]:
        cursor = "*"
        fetched = 0
        last_cursor = cursor
        while fetched < max_reviews:
            page = _steam_reviews_page(appid, cursor=cursor, num_per_page=100, filter_type=filter_type)
            reviews = page["reviews"]
            if not reviews:
                break
            now_ts = datetime.now(UTC).isoformat()
            with get_connection() as conn:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO app_reviews (
                        review_id, appid, voted_up, votes_up, votes_funny,
                        weighted_vote_score, steam_purchase, received_for_free,
                        written_during_early_access, author_playtime_forever,
                        author_playtime_last_two_weeks, review, timestamp_created, fetched_at
                    ) VALUES (
                        :review_id, :appid, :voted_up, :votes_up, :votes_funny,
                        :weighted_vote_score, :steam_purchase, :received_for_free,
                        :written_during_early_access, :author_playtime_forever,
                        :author_playtime_last_two_weeks, :review, :timestamp_created, :fetched_at
                    )
                    """,
                    [
                        {
                            **r,
                            "review_id": r["recommendationid"],
                            "appid": appid,
                            "fetched_at": now_ts,
                            "author_playtime_forever": (r.get("author") or {}).get("playtime_forever"),
                            "author_playtime_last_two_weeks": (r.get("author") or {}).get("playtime_last_two_weeks"),
                        }
                        for r in reviews
                    ],
                )
            fetched += len(reviews)
            last_cursor = page["cursor"]
            if on_progress:
                on_progress(fetched, max_reviews)
            next_cursor = page["cursor"]
            if next_cursor == cursor or not next_cursor:
                break
            cursor = next_cursor
            time.sleep(sleep)
        return fetched, last_cursor

    def _close_review_session(self, session_id: int, fetched: int, last_cursor: str, status: str) -> None:
        done = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE review_fetch_sessions SET completed_at=?, reviews_fetched=?, last_cursor=?, status=? WHERE id=?",
                (done, fetched, last_cursor, status, session_id),
            )

    def fetch_reviews(
        self,
        appid: int,
        max_reviews: int = 10000,
        filter_type: str = "all",
        sleep: float = 1.0,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict:
        """Paginate Steam review texts for appid and upsert into app_reviews.

        Opens a review_fetch_sessions row, paginates until max_reviews reached
        or cursor exhausted, then closes the session. Safe to re-run; INSERT OR
        IGNORE prevents duplicates. Returns {"session_id": int, "reviews_fetched": int}.
        """
        session_id = self._open_review_session(appid, filter_type, max_reviews)
        fetched, last_cursor = 0, "*"
        try:
            fetched, last_cursor = self._paginate_reviews(appid, max_reviews, filter_type, sleep, on_progress)
            status = "complete"
        except Exception:
            status = "failed"
            raise
        finally:
            self._close_review_session(session_id, fetched, last_cursor, status)
        return {"session_id": session_id, "reviews_fetched": fetched}

    def get_reviews(self, appid: int, min_words: int = 10) -> list[dict]:
        """Return stored review texts for appid meeting the minimum word count."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT review_id, review, voted_up, votes_up, author_playtime_forever FROM app_reviews WHERE appid = ?",
                (appid,),
            ).fetchall()
        return [dict(r) for r in rows if len(r["review"].split()) >= min_words]

    def get_review_fetch_status(self, appid: int) -> dict | None:
        """Return the most recent review_fetch_sessions row for appid, or None."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM review_fetch_sessions WHERE appid = ? ORDER BY id DESC LIMIT 1",
                (appid,),
            ).fetchone()
        return dict(row) if row else None

    # ── Topic Runs ────────────────────────────────────────────────────────────

    def create_topic_run(
        self,
        appid: int,
        embedding_model: str,
        llm_model: str,
        hdbscan_params: dict,
        chroma_collection: str,
    ) -> int:
        """Insert a running review_topic_runs row and return its id."""
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO review_topic_runs
                    (appid, started_at, embedding_model, llm_model, hdbscan_params, chroma_collection)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (appid, now, embedding_model, llm_model, json.dumps(hdbscan_params), chroma_collection),
            )
            return cur.lastrowid

    def update_topic_run(self, run_id: int, **fields) -> None:
        """Update arbitrary fields on a review_topic_runs row."""
        if not fields:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        with get_connection() as conn:
            conn.execute(
                f"UPDATE review_topic_runs SET {set_clause} WHERE id = :_id",
                {**fields, "_id": run_id},
            )

    def save_topics(self, run_id: int, appid: int, topics: list[dict]) -> list[int]:
        """Bulk-insert topics for a run. Returns list of inserted topic ids."""
        now = datetime.now(UTC).isoformat()
        ids = []
        with get_connection() as conn:
            for t in topics:
                cur = conn.execute(
                    """
                    INSERT INTO review_topics
                        (run_id, appid, cluster_label, category_name, description,
                         review_count, sample_review_ids, centroid_vector, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        appid,
                        t["cluster_label"],
                        t.get("category_name"),
                        t.get("description"),
                        t["review_count"],
                        json.dumps(t.get("sample_review_ids") or []),
                        json.dumps(t["centroid_vector"]) if t.get("centroid_vector") is not None else None,
                        now,
                    ),
                )
                ids.append(cur.lastrowid)
        return ids

    def save_topic_assignments(self, run_id: int, assignments: list[dict]) -> None:
        """Bulk-upsert review_topic_assignments rows."""
        now = datetime.now(UTC).isoformat()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO review_topic_assignments
                    (review_id, run_id, topic_id, similarity_score, is_noise, assigned_at)
                VALUES (:review_id, :run_id, :topic_id, :similarity_score, :is_noise, :assigned_at)
                ON CONFLICT(review_id, run_id) DO UPDATE SET
                    topic_id = excluded.topic_id,
                    similarity_score = excluded.similarity_score,
                    is_noise = excluded.is_noise,
                    assigned_at = excluded.assigned_at
                """,
                [
                    {
                        "review_id": a["review_id"],
                        "run_id": run_id,
                        "topic_id": a.get("topic_id"),
                        "similarity_score": a.get("similarity_score"),
                        "is_noise": int(bool(a.get("is_noise", False))),
                        "assigned_at": now,
                    }
                    for a in assignments
                ],
            )

    def resolve_run_id(self, appid: int, run_id: int | None) -> int | None:
        """Return run_id if provided, otherwise the latest run id for appid, or None if no runs exist."""
        if run_id is not None:
            return run_id
        runs = self.get_topic_runs(appid)
        return runs[0]["id"] if runs else None

    def get_topic_runs(self, appid: int) -> list[dict]:
        """Return all review_topic_runs for appid, newest first."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM review_topic_runs WHERE appid = ? ORDER BY id DESC",
                (appid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_topics(self, run_id: int) -> list[dict]:
        """Return all review_topics rows for a run."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM review_topics WHERE run_id = ? ORDER BY cluster_label",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_review_topics_status(self, appid: int) -> dict:
        """Return a summary dict for appid: review count, latest run, topics, uncategorized count."""
        with get_connection() as conn:
            review_count = conn.execute("SELECT COUNT(*) FROM app_reviews WHERE appid = ?", (appid,)).fetchone()[0]

            run_row = conn.execute(
                "SELECT * FROM review_topic_runs WHERE appid = ? ORDER BY id DESC LIMIT 1",
                (appid,),
            ).fetchone()

        latest_run = dict(run_row) if run_row else None
        topics = []
        uncategorized_count = 0

        if latest_run:
            topics = self.get_topics(latest_run["id"])
            with get_connection() as conn:
                uncategorized_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM app_reviews ar
                    WHERE ar.appid = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM review_topic_assignments rta
                          WHERE rta.review_id = ar.review_id
                            AND rta.run_id = ?
                            AND rta.is_noise = 0
                      )
                    """,
                    (appid, latest_run["id"]),
                ).fetchone()[0]

        return {
            "review_count": review_count,
            "latest_run": latest_run,
            "topics": topics,
            "uncategorized_count": uncategorized_count,
        }
