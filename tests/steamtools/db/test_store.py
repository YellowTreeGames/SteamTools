"""Tests for steamtools.db.store — all Steam API calls are mocked."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from steamtools.db.connection import get_connection
from steamtools.db.store import StoDB

_NOW = datetime.now(UTC)


def _iso(dt=None):
    return (dt or _NOW).isoformat()


def _days_ago(n):
    return _iso(_NOW - timedelta(days=n))


# ── DB seed helpers ───────────────────────────────────────────────────────────


def _app(appid=1, name="Test Game"):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, name, _iso()),
        )


def _details(appid=1, fetched_at=None, coming_soon=0, release_date="2020-01-01", **extra):
    row = {
        "type": "game",
        "name": "Test Game",
        "is_free": 0,
        "coming_soon": coming_soon,
        "release_date": release_date,
        "fetched_at": fetched_at or _iso(),
        **extra,
    }
    cols = ", ".join(row.keys())
    ph = ", ".join("?" * len(row))
    with get_connection() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO app_details (appid, {cols}) VALUES (?, {ph})",
            (appid, *row.values()),
        )


def _review_counts(appid=1, fetched_at=None, total_reviews=100):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_review_counts "
            "(appid, total_reviews, total_positive, total_negative, review_score, review_score_desc, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (appid, total_reviews, 80, 20, 8, "Very Positive", fetched_at or _iso()),
        )


def _review(appid=1, review_id="r1", text="This is a great game worth playing lots"):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO app_reviews (review_id, appid, review, fetched_at) VALUES (?, ?, ?, ?)",
            (review_id, appid, text, _iso()),
        )


_GAME_DATA = {
    "type": "game",
    "name": "Test Game",
    "is_free": False,
    "short_description": "A test.",
    "detailed_description": "Detailed.",
    "about_the_game": "About.",
    "supported_languages": "English",
    "header_image": "http://img.jpg",
    "website": "http://x.com",
    "required_age": 0,
    "release_date": {"date": "Jan 01, 2020", "coming_soon": False},
    "platforms": {"windows": True, "mac": False, "linux": False},
    "developers": ["Dev"],
    "publishers": ["Pub"],
    "genres": [{"description": "Action"}],
    "categories": [{"description": "Single-player"}],
    "price_overview": {"currency": "USD", "initial": 1000, "final": 1000, "discount_percent": 0},
    "metacritic": {"score": 75},
    "achievements": {"total": 10},
    "dlc": [],
    "screenshots": [],
    "movies": [],
    "content_descriptors": {},
    "background": "http://bg.jpg",
}

_REVIEW_DATA = {
    "total_reviews": 100,
    "total_positive": 80,
    "total_negative": 20,
    "review_score": 8,
    "review_score_desc": "Very Positive",
}


# ── search_apps ───────────────────────────────────────────────────────────────


def test_search_apps_no_results():
    db = StoDB()
    assert db.search_apps("nonexistent") == []


def test_search_apps_match():
    _app(1, "Hollow Knight")
    db = StoDB()
    results = db.search_apps("Hollow")
    assert len(results) == 1
    assert results[0]["name"] == "Hollow Knight"


def test_search_apps_with_details():
    _app(1)
    _details(1)
    db = StoDB()
    results = db.search_apps("Test")
    assert results[0]["has_details"] == 1


# ── app_stats ─────────────────────────────────────────────────────────────────


def test_app_stats_empty():
    db = StoDB()
    s = db.app_stats()
    assert s["total"] == 0
    assert s["with_details"] == 0


def test_app_stats_counts():
    _app(1)
    _app(2)
    _details(1)
    db = StoDB()
    s = db.app_stats()
    assert s["total"] == 2
    assert s["with_details"] == 1


# ── app_details_stats ─────────────────────────────────────────────────────────


def test_app_details_stats_empty():
    db = StoDB()
    s = db.app_details_stats()
    assert s["total"] == 0


def test_app_details_stats_with_data():
    _app(1)
    _details(1)
    db = StoDB()
    s = db.app_details_stats()
    assert s["total"] == 1
    assert s["last_appid"] == 1


# ── sync_app_list ─────────────────────────────────────────────────────────────


def test_sync_app_list_full(mocker):
    mocker.patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "A"}])
    db = StoDB()
    n = db.sync_app_list()
    assert n == 1
    assert db.search_apps("A") != []


def test_sync_app_list_partial(mocker):
    mocker.patch(
        "steamtools.db.store._steam_app_list_page",
        return_value={"apps": [{"appid": 2, "name": "B"}]},
    )
    _app(1)  # ensure MAX(appid) = 1
    db = StoDB()
    n = db.sync_app_list(count=5)
    assert n == 1


def test_sync_app_list_upserts(mocker):
    mocker.patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "Updated"}])
    _app(1, "Original")
    db = StoDB()
    db.sync_app_list()
    results = db.search_apps("Updated")
    assert len(results) == 1


# ── sync_app_details_one ──────────────────────────────────────────────────────


def test_sync_app_details_one_game(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=_GAME_DATA)
    _app(1)
    db = StoDB()
    result = db.sync_app_details_one(1, force=True)
    assert result["status"] == "game"
    assert result["row"]["name"] == "Test Game"


def test_sync_app_details_one_not_a_game(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value={"type": "dlc", "name": "A DLC"})
    _app(1)
    db = StoDB()
    result = db.sync_app_details_one(1, force=True)
    assert result["status"] == "not_a_game"
    assert result["detected_type"] == "dlc"
    # App is removed from apps table
    assert db.search_apps("Test") == []


def test_sync_app_details_one_no_data(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=None)
    _app(1)
    db = StoDB()
    result = db.sync_app_details_one(1, force=True)
    assert result["status"] == "not_a_game"
    assert result["detected_type"] is None


def test_sync_app_details_one_already_current():
    _app(1)
    _details(1, fetched_at=_iso())  # fresh
    db = StoDB()
    result = db.sync_app_details_one(1, force=False)
    assert result["status"] == "already_current"


# ── get_app_details ───────────────────────────────────────────────────────────


def test_get_app_details_no_auto_sync():
    _app(1)
    _details(1)
    db = StoDB()
    result = db.get_app_details([1], auto_sync=False)
    assert result[1]["name"] == "Test Game"


def test_get_app_details_auto_sync_triggers_refresh(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=_GAME_DATA)
    _app(1)
    _details(1, fetched_at=_days_ago(35))  # stale
    db = StoDB()
    result = db.get_app_details([1], auto_sync=True)
    assert result[1] is not None


def test_get_app_details_missing_appid_returns_none(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=None)
    _app(1)
    db = StoDB()
    result = db.get_app_details([1], auto_sync=True)
    assert result[1] is None


# ── sync_app_details ──────────────────────────────────────────────────────────


def test_sync_app_details_no_limit(mocker):
    mock = mocker.patch("steamtools.db.store._steam_app_details", return_value=_GAME_DATA)
    _app(1)
    db = StoDB()
    n = db.sync_app_details()
    assert n == 1
    mock.assert_called_once_with(1)


def test_sync_app_details_with_limit(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=_GAME_DATA)
    _app(1)
    _app(2, "Game Two")
    db = StoDB()
    n = db.sync_app_details(limit=1)
    assert n == 1


def test_sync_app_details_with_progress(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value=_GAME_DATA)
    _app(1)
    calls = []
    db = StoDB()
    db.sync_app_details(on_progress=lambda i, total, appid, result: calls.append(i))
    assert calls == [1]


# ── _row_from_details ─────────────────────────────────────────────────────────


def test_row_from_details_full():
    row = StoDB._row_from_details(1, _GAME_DATA)
    assert row["appid"] == 1
    assert row["name"] == "Test Game"
    assert row["type"] == "game"
    assert row["genres"] == json.dumps(["Action"])
    assert row["platforms_windows"] == 1
    assert row["price_initial"] == 1000


def test_row_from_details_minimal():
    row = StoDB._row_from_details(1, {"type": "game", "name": "Minimal"})
    assert row["required_age"] is None  # required_age=0 → falsy → None
    assert row["genres"] == "[]"
    assert row["price_initial"] is None


# ── review counts ─────────────────────────────────────────────────────────────


def test_get_review_counts_no_auto_sync():
    _app(1)
    _review_counts(1)
    db = StoDB()
    result = db.get_review_counts([1], auto_sync=False)
    assert result[1]["total_reviews"] == 100


def test_get_review_counts_auto_sync_stale(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=_REVIEW_DATA)
    _app(1)
    _details(1)
    _review_counts(1, fetched_at=_days_ago(35))  # stale
    db = StoDB()
    result = db.get_review_counts([1], auto_sync=True)
    assert result[1] is not None


def test_get_review_counts_auto_sync_fresh():
    _app(1)
    _details(1)
    _review_counts(1)
    db = StoDB()
    result = db.get_review_counts([1], auto_sync=True)
    assert result[1]["total_reviews"] == 100


def test_sync_review_counts_all(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=_REVIEW_DATA)
    _app(1)
    _details(1)
    db = StoDB()
    n = db.sync_review_counts()
    assert n == 1


def test_sync_review_counts_with_appids(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=_REVIEW_DATA)
    _app(1)
    _details(1)
    db = StoDB()
    n = db.sync_review_counts(appids=[1])
    assert n == 1


def test_sync_review_counts_no_data(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=None)
    _app(1)
    _details(1)
    db = StoDB()
    n = db.sync_review_counts(appids=[1])
    assert n == 0


def test_sync_review_counts_with_limit(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=_REVIEW_DATA)
    _app(1)
    _app(2, "G2")
    _details(1)
    _details(2)
    db = StoDB()
    n = db.sync_review_counts(limit=1)
    assert n == 1


def test_sync_review_counts_with_progress(mocker):
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=_REVIEW_DATA)
    _app(1)
    _details(1)
    calls = []
    db = StoDB()
    db.sync_review_counts(on_progress=lambda i, t, aid, d: calls.append(i))
    assert 1 in calls


def test_review_stats():
    _app(1)
    _review_counts(1)
    db = StoDB()
    s = db.review_stats()
    assert s["total"] == 1


# ── get_stale_review_appids_for_evals ─────────────────────────────────────────


def test_get_stale_review_appids_for_evals_empty():
    db = StoDB()
    assert db.get_stale_review_appids_for_evals() == []


def test_get_stale_review_appids_for_evals_stale():
    _app(1)
    _details(1)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO eval_results (appid, eval_type, eval_number, score, rationale, model, evaled_at) "
            "VALUES (1, 1, 1, 4.0, 'good', 'model', ?)",
            (_iso(),),
        )
    db = StoDB()
    stale = db.get_stale_review_appids_for_evals()
    assert 1 in stale


# ── get_game_view ─────────────────────────────────────────────────────────────


def test_get_game_view_found():
    _app(1)
    _details(1)
    db = StoDB()
    view = db.get_game_view(1)
    assert view is not None
    assert view["name"] == "Test Game"


def test_get_game_view_not_found():
    db = StoDB()
    assert db.get_game_view(9999) is None


# ── eval helpers ──────────────────────────────────────────────────────────────


def test_get_eval_type_found():
    db = StoDB()
    t = db.get_eval_type("Appeal")
    assert t["name"] == "Appeal"


def test_get_eval_type_not_found():
    db = StoDB()
    with pytest.raises(ValueError, match="Unknown eval type"):
        db.get_eval_type("Nonexistent")


def test_save_eval_result_and_increment():
    _app(1)
    db = StoDB()
    n1 = db.save_eval_result(1, 1, 4.0, "Good", "model-x")
    n2 = db.save_eval_result(1, 1, 3.5, "OK", "model-x")
    assert n1 == 1
    assert n2 == 2


def test_get_eval_correlation_data_empty():
    db = StoDB()
    assert db.get_eval_correlation_data(1) == []


def test_get_eval_correlation_data_with_data():
    _app(1)
    _review_counts(1)
    db = StoDB()
    db.save_eval_result(1, 1, 4.0, "Good", "m")
    rows = db.get_eval_correlation_data(1)
    assert len(rows) == 1
    assert rows[0]["avg_score"] == 4.0


def test_has_app_details_false():
    db = StoDB()
    assert db.has_app_details() is False


def test_has_app_details_true():
    _app(1)
    _details(1)
    db = StoDB()
    assert db.has_app_details() is True


# ── get_pending_eval_games ────────────────────────────────────────────────────


def test_get_pending_eval_games_with_appids():
    _app(1)
    _details(1, short_description="A cool game.")
    _review_counts(1)
    db = StoDB()
    games = db.get_pending_eval_games(1, [1])
    assert len(games) == 1


def test_get_pending_eval_games_without_appids():
    _app(1)
    _details(1, short_description="A cool game.")
    _review_counts(1)
    db = StoDB()
    games = db.get_pending_eval_games(1, [], n=5)
    assert len(games) == 1


def test_get_pending_eval_games_fill_mode():
    _app(1)
    _details(1, short_description="A cool game.")
    _review_counts(1)
    db = StoDB()
    db.save_eval_result(1, 1, 4.0, "OK", "m")
    games = db.get_pending_eval_games(1, [], fill=True, max_scores=5)
    assert any(g["appid"] == 1 for g in games)


def test_get_pending_eval_games_excludes_coming_soon():
    _app(1)
    _details(1, coming_soon=1, short_description="Coming soon!")
    _review_counts(1)
    db = StoDB()
    games = db.get_pending_eval_games(1, [1])
    assert games == []


# ── fetch_reviews ─────────────────────────────────────────────────────────────

_PAGE = {
    "reviews": [
        {
            "recommendationid": "r1",
            "voted_up": True,
            "votes_up": 1,
            "votes_funny": 0,
            "weighted_vote_score": 0.9,
            "steam_purchase": True,
            "received_for_free": False,
            "written_during_early_access": False,
            "author_playtime_forever": 10,
            "author_playtime_last_two_weeks": 2,
            "review": "Great!",
            "timestamp_created": 0,
        }
    ],
    "cursor": "next",
    "total_reviews": 1,
}


def test_fetch_reviews_success(mocker):
    mocker.patch(
        "steamtools.db.store._steam_reviews_page",
        side_effect=[_PAGE, {**_PAGE, "cursor": "next", "reviews": []}],
    )
    _app(1)
    db = StoDB()
    result = db.fetch_reviews(1, max_reviews=100)
    assert result["reviews_fetched"] == 1


def test_fetch_reviews_cursor_repeat_stops(mocker):
    repeated = {**_PAGE, "cursor": "*"}
    mocker.patch("steamtools.db.store._steam_reviews_page", return_value=repeated)
    _app(1)
    db = StoDB()
    result = db.fetch_reviews(1, max_reviews=100)
    assert result["reviews_fetched"] == 1


def test_fetch_reviews_max_reviews_cap(mocker):
    mocker.patch("steamtools.db.store._steam_reviews_page", return_value={**_PAGE, "cursor": "c2"})
    _app(1)
    db = StoDB()
    result = db.fetch_reviews(1, max_reviews=1)
    assert result["reviews_fetched"] == 1


def test_fetch_reviews_with_progress(mocker):
    mocker.patch(
        "steamtools.db.store._steam_reviews_page",
        side_effect=[_PAGE, {**_PAGE, "reviews": []}],
    )
    _app(1)
    calls = []
    db = StoDB()
    db.fetch_reviews(1, max_reviews=100, on_progress=lambda f, t: calls.append(f))
    assert calls == [1]


def test_fetch_reviews_exception_sets_failed_status(mocker):
    mocker.patch("steamtools.db.store._steam_reviews_page", side_effect=RuntimeError("boom"))
    _app(1)
    db = StoDB()
    with pytest.raises(RuntimeError, match="boom"):
        db.fetch_reviews(1)
    status = db.get_review_fetch_status(1)
    assert status["status"] == "failed"


# ── get_reviews ───────────────────────────────────────────────────────────────


def test_get_reviews_empty():
    _app(1)
    db = StoDB()
    assert db.get_reviews(1) == []


def test_get_reviews_with_min_words():
    _app(1)
    _review(1, "r1", "short")  # < 10 words, filtered out
    _review(1, "r2", " ".join(["word"] * 15))  # passes
    db = StoDB()
    result = db.get_reviews(1, min_words=10)
    assert len(result) == 1
    assert result[0]["review_id"] == "r2"


# ── get_review_fetch_status ───────────────────────────────────────────────────


def test_get_review_fetch_status_none():
    db = StoDB()
    assert db.get_review_fetch_status(9999) is None


def test_get_review_fetch_status_found(mocker):
    mocker.patch("steamtools.db.store._steam_reviews_page", side_effect=[_PAGE, {**_PAGE, "reviews": []}])
    _app(1)
    db = StoDB()
    db.fetch_reviews(1)
    status = db.get_review_fetch_status(1)
    assert status is not None
    assert status["appid"] == 1


# ── topic run CRUD ────────────────────────────────────────────────────────────


def test_create_and_get_topic_run():
    _app(1)
    db = StoDB()
    run_id = db.create_topic_run(1, "model-a", "llm-b", {"min_cluster_size": 10}, "col_1")
    assert run_id is not None
    runs = db.get_topic_runs(1)
    assert len(runs) == 1
    assert runs[0]["id"] == run_id


def test_update_topic_run():
    _app(1)
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    db.update_topic_run(run_id, status="complete", clusters_found=3)
    runs = db.get_topic_runs(1)
    assert runs[0]["status"] == "complete"


def test_update_topic_run_no_fields():
    _app(1)
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    db.update_topic_run(run_id)  # should be a no-op
    runs = db.get_topic_runs(1)
    assert runs[0]["status"] == "running"


def test_save_and_get_topics():
    _app(1)
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    topics = [
        {
            "cluster_label": 0,
            "category_name": "Gameplay",
            "description": "Fun.",
            "review_count": 10,
            "sample_review_ids": ["r1"],
            "centroid_vector": [0.1, 0.2],
        },
    ]
    ids = db.save_topics(run_id, 1, topics)
    assert len(ids) == 1
    fetched = db.get_topics(run_id)
    assert fetched[0]["category_name"] == "Gameplay"


def test_save_topics_without_centroid():
    _app(1)
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    topics = [
        {
            "cluster_label": 0,
            "category_name": "T",
            "description": "D",
            "review_count": 5,
            "sample_review_ids": [],
            "centroid_vector": None,
        }
    ]
    ids = db.save_topics(run_id, 1, topics)
    assert len(ids) == 1


def test_save_topic_assignments():
    _app(1)
    _review(1, "r1")
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    topic_ids = db.save_topics(
        run_id,
        1,
        [
            {
                "cluster_label": 0,
                "category_name": "T",
                "description": "D",
                "review_count": 1,
                "sample_review_ids": ["r1"],
                "centroid_vector": [0.0],
            }
        ],
    )
    db.save_topic_assignments(
        run_id,
        [
            {"review_id": "r1", "topic_id": topic_ids[0], "similarity_score": 0.9, "is_noise": False},
        ],
    )
    # upsert again
    db.save_topic_assignments(
        run_id,
        [
            {"review_id": "r1", "topic_id": topic_ids[0], "similarity_score": 0.95, "is_noise": False},
        ],
    )


# ── get_review_topics_status ──────────────────────────────────────────────────


def test_get_review_topics_status_no_run():
    _app(1)
    db = StoDB()
    s = db.get_review_topics_status(1)
    assert s["review_count"] == 0
    assert s["latest_run"] is None
    assert s["topics"] == []
    assert s["uncategorized_count"] == 0


def test_get_review_topics_status_with_run():
    _app(1)
    _review(1, "r1")
    db = StoDB()
    run_id = db.create_topic_run(1, "m", "l", {}, "c")
    db.update_topic_run(run_id, status="complete", clusters_found=1)
    db.save_topics(
        run_id,
        1,
        [
            {
                "cluster_label": 0,
                "category_name": "T",
                "description": "D",
                "review_count": 1,
                "sample_review_ids": ["r1"],
                "centroid_vector": [0.0],
            }
        ],
    )
    s = db.get_review_topics_status(1)
    assert s["latest_run"]["id"] == run_id
    assert len(s["topics"]) == 1
    assert s["uncategorized_count"] == 1  # r1 not assigned
