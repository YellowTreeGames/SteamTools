"""Tests for steamtools_mcp.server — MCP tool functions called directly."""

from datetime import UTC, datetime

from steamtools.db.connection import get_connection
from steamtools_mcp.server import (
    classify_review_topics,
    discover_review_topics,
    fetch_review_texts,
    get_app_details,
    get_game,
    get_review_topics_status,
    search_games,
)


def _now():
    return datetime.now(UTC).isoformat()


def _app(appid=1, name="Test Game"):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, name, _now()),
        )


def _details(appid=1):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_details "
            "(appid, type, name, is_free, coming_soon, release_date, fetched_at) "
            "VALUES (?, 'game', 'Test Game', 0, 0, '2020-01-01', ?)",
            (appid, _now()),
        )


# ── search_games ──────────────────────────────────────────────────────────────


def test_search_games_empty():
    assert search_games("xyz") == []


def test_search_games_returns_match():
    _app(1, "Portal")
    results = search_games("Portal")
    assert any(r["name"] == "Portal" for r in results)


# ── get_app_details ───────────────────────────────────────────────────────────


def test_get_app_details_already_current():
    _app(1)
    _details(1)
    result = get_app_details(1, force=False)
    assert result["status"] == "already_current"


def test_get_app_details_force(mocker):
    _app(1)
    mocker.patch(
        "steamtools.db.store._steam_app_details",
        return_value={
            "type": "game",
            "name": "Test",
            "is_free": False,
            "release_date": {"date": "2020-01-01", "coming_soon": False},
            "platforms": {},
            "developers": [],
            "publishers": [],
            "genres": [],
            "categories": [],
        },
    )
    result = get_app_details(1, force=True)
    assert result["status"] == "game"


# ── get_game ──────────────────────────────────────────────────────────────────


def test_get_game_not_found():
    assert get_game(9999) is None


def test_get_game_found():
    _app(1)
    _details(1)
    result = get_game(1)
    assert result is not None
    assert result["name"] == "Test Game"


# ── fetch_review_texts ────────────────────────────────────────────────────────


def test_fetch_review_texts(mocker):
    _app(1)
    page = {
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
                "author": {"playtime_forever": 5, "playtime_last_two_weeks": 1},
                "review": "Fun!",
                "timestamp_created": 0,
            }
        ],
        "cursor": "next",
        "total_reviews": 1,
    }
    mocker.patch(
        "steamtools.db.store._steam_reviews_page",
        side_effect=[page, {**page, "reviews": []}],
    )
    result = fetch_review_texts(1, max_reviews=10)
    assert result["reviews_fetched"] == 1


# ── discover_review_topics ────────────────────────────────────────────────────


def test_discover_review_topics(mocker):
    _app(1)
    mock_result = {
        "run_id": 1,
        "clusters_found": 1,
        "noise_count": 0,
        "topics": [{"category_name": "Fun", "review_count": 3}],
    }
    mocker.patch("steamtools.review_topics.pipeline.ReviewTopicPipeline.run_discovery", return_value=mock_result)
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = discover_review_topics(1)
    assert result["clusters_found"] == 1


# ── classify_review_topics ────────────────────────────────────────────────────


def test_classify_review_topics_no_runs():
    _app(1)
    result = classify_review_topics(1)
    assert "error" in result


def test_classify_review_topics_with_run(mocker):
    _app(1)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO review_topic_runs "
            "(appid, started_at, status, reviews_embedded, embedding_model, llm_model, hdbscan_params, chroma_collection) "
            "VALUES (1, ?, 'complete', 0, 'm', 'l', '{}', 'c')",
            (_now(),),
        )
    mocker.patch(
        "steamtools.review_topics.pipeline.ReviewTopicPipeline.classify_reviews",
        return_value={"assigned": 2, "uncategorized": 0},
    )
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = classify_review_topics(1)
    assert result["assigned"] == 2


def test_classify_review_topics_explicit_run_id(mocker):
    _app(1)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO review_topic_runs "
            "(appid, started_at, status, reviews_embedded, embedding_model, llm_model, hdbscan_params, chroma_collection) "
            "VALUES (1, ?, 'complete', 0, 'm', 'l', '{}', 'c')",
            (_now(),),
        )
    mocker.patch(
        "steamtools.review_topics.pipeline.ReviewTopicPipeline.classify_reviews",
        return_value={"assigned": 1, "uncategorized": 1},
    )
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = classify_review_topics(1, run_id=1)
    assert result["assigned"] == 1


# ── get_review_topics_status ──────────────────────────────────────────────────


def test_get_review_topics_status():
    _app(1)
    result = get_review_topics_status(1)
    assert result["review_count"] == 0
    assert result["latest_run"] is None
