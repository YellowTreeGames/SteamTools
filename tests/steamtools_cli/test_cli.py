"""Tests for steamtools_cli.cli — all Steam API and LLM calls are mocked."""

from datetime import UTC, datetime

from typer.testing import CliRunner

from steamtools.db.connection import get_connection
from steamtools_cli.cli import app

runner = CliRunner()


def _now():
    return datetime.now(UTC).isoformat()


def _app(appid=1, name="Test Game"):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, name, _now()),
        )


def _details(appid=1, short_description="A cool game."):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_details "
            "(appid, type, name, is_free, coming_soon, release_date, short_description, fetched_at) "
            "VALUES (?, 'game', 'Test Game', 0, 0, '2020-01-01', ?, ?)",
            (appid, short_description, _now()),
        )


def _review_counts(appid=1):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_review_counts "
            "(appid, total_reviews, total_positive, total_negative, review_score, review_score_desc, fetched_at) "
            "VALUES (?, 200, 160, 40, 8, 'Very Positive', ?)",
            (appid, _now()),
        )


# ── app info / search / fetch ─────────────────────────────────────────────────


def test_app_info_empty():
    result = runner.invoke(app, ["app", "info"])
    assert result.exit_code == 0
    assert "Apps: 0" in result.output


def test_app_info_with_data():
    _app()
    result = runner.invoke(app, ["app", "info"])
    assert "Apps: 1" in result.output


def test_app_search_no_results():
    result = runner.invoke(app, ["app", "search", "nonexistent"])
    assert result.exit_code == 0
    assert "No games found" in result.output


def test_app_search_with_results():
    _app(1, "Hollow Knight")
    result = runner.invoke(app, ["app", "search", "Hollow"])
    assert "Hollow Knight" in result.output


def test_app_fetch_full(mocker):
    mocker.patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "A"}])
    result = runner.invoke(app, ["app", "fetch"])
    assert result.exit_code == 0
    assert "Upserted 1 apps" in result.output


def test_app_fetch_partial(mocker):
    mocker.patch(
        "steamtools.db.store._steam_app_list_page",
        return_value={"apps": [{"appid": 1, "name": "A"}]},
    )
    result = runner.invoke(app, ["app", "fetch", "--count", "5"])
    assert result.exit_code == 0
    assert "Upserted 1 apps" in result.output


# ── app-details ───────────────────────────────────────────────────────────────


def test_app_details_info():
    result = runner.invoke(app, ["app-details", "info"])
    assert result.exit_code == 0
    assert "App details: 0" in result.output


def test_details_fetch_single_game(mocker):
    _app(1)
    mocker.patch(
        "steamtools.db.store._steam_app_details",
        return_value={
            "type": "game",
            "name": "Test Game",
            "is_free": False,
            "release_date": {"date": "2020-01-01", "coming_soon": False},
            "platforms": {},
            "developers": [],
            "publishers": [],
            "genres": [],
            "categories": [],
        },
    )
    result = runner.invoke(app, ["app-details", "fetch", "--appid", "1"])
    assert result.exit_code == 0
    assert "status=game" in result.output


def test_details_fetch_single_not_a_game(mocker):
    _app(1)
    mocker.patch("steamtools.db.store._steam_app_details", return_value={"type": "dlc"})
    result = runner.invoke(app, ["app-details", "fetch", "--appid", "1"])
    assert "status=not_a_game" in result.output


def test_details_fetch_single_already_current():
    _app(1)
    _details(1)
    result = runner.invoke(app, ["app-details", "fetch", "--appid", "1"])
    assert "already_current" in result.output


def test_details_fetch_force_requires_appid():
    result = runner.invoke(app, ["app-details", "fetch", "--force"])
    assert result.exit_code != 0


def test_details_fetch_appid_and_count_error():
    result = runner.invoke(app, ["app-details", "fetch", "--appid", "1", "--count", "5"])
    assert result.exit_code != 0


def test_details_fetch_batch_with_progress(mocker):
    mocker.patch(
        "steamtools.db.store._steam_app_details",
        return_value={
            "type": "game",
            "name": "G",
            "is_free": False,
            "release_date": {"date": "2020-01-01", "coming_soon": False},
            "platforms": {},
            "developers": [],
            "publishers": [],
            "genres": [],
            "categories": [],
        },
    )
    _app(1)
    result = runner.invoke(app, ["app-details", "fetch"])
    assert "Processed 1 apps" in result.output


def test_details_fetch_batch_not_a_game_progress(mocker):
    mocker.patch("steamtools.db.store._steam_app_details", return_value={"type": "dlc"})
    _app(1)
    result = runner.invoke(app, ["app-details", "fetch"])
    assert "Processed 1 apps" in result.output


# ── app-reviews ───────────────────────────────────────────────────────────────


def test_app_reviews_info():
    result = runner.invoke(app, ["app-reviews", "info"])
    assert result.exit_code == 0
    assert "Review counts: 0" in result.output


def test_reviews_fetch(mocker):
    _app(1)
    _details(1)
    mocker.patch(
        "steamtools.db.store._steam_review_counts",
        return_value={
            "total_reviews": 50,
            "total_positive": 40,
            "total_negative": 10,
            "review_score": 7,
            "review_score_desc": "Mostly Positive",
        },
    )
    result = runner.invoke(app, ["app-reviews", "fetch", "--count", "1"])
    assert result.exit_code == 0
    assert "Synced" in result.output


def test_reviews_fetch_no_data_progress(mocker):
    _app(1)
    _details(1)
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=None)
    result = runner.invoke(app, ["app-reviews", "fetch"])
    assert "Synced 0 review counts" in result.output


def test_reviews_fetch_text(mocker):
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
                "author_playtime_forever": 10,
                "author_playtime_last_two_weeks": 2,
                "review": "Great game!",
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
    result = runner.invoke(app, ["app-reviews", "fetch-text", "1"])
    assert result.exit_code == 0
    assert "reviews_fetched=1" in result.output


# ── ai eval ───────────────────────────────────────────────────────────────────


def test_eval_short_description_no_games(capsys):
    result = runner.invoke(app, ["ai", "eval", "short-description"])
    assert result.exit_code == 0


def test_eval_short_description_runs(mocker):
    _app(1)
    _details(1)
    _review_counts(1)
    mocker.patch(
        "steamtools.ai.eval.gemini_client.evaluate",
        return_value={"score": 4.0, "rationale": "Great."},
    )
    result = runner.invoke(app, ["ai", "eval", "short-description", "-n", "1"])
    assert result.exit_code == 0


def test_eval_short_description_show_eval(mocker):
    _app(1)
    _details(1)
    _review_counts(1)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO eval_results (appid, eval_type, eval_number, score, rationale, model, evaled_at) "
            "VALUES (1, 1, 1, 4.0, 'OK', 'model', ?)",
            (_now(),),
        )
    mocker.patch("steamtools.ai.eval.plt.show")
    mocker.patch("steamtools.ai.eval.plt.figure")
    mocker.patch("steamtools.ai.eval.plt.scatter")
    mocker.patch("steamtools.ai.eval.plt.plot")
    mocker.patch("steamtools.ai.eval.plt.xlabel")
    mocker.patch("steamtools.ai.eval.plt.ylabel")
    mocker.patch("steamtools.ai.eval.plt.title")
    mocker.patch("steamtools.ai.eval.plt.tight_layout")
    result = runner.invoke(app, ["ai", "eval", "plot"])
    assert result.exit_code == 0


def test_eval_sync_no_stale():
    result = runner.invoke(app, ["ai", "eval", "sync"])
    assert result.exit_code == 0
    assert "fresh" in result.output


def test_eval_sync_with_stale(mocker):
    _app(1)
    _details(1)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO eval_results (appid, eval_type, eval_number, score, rationale, model, evaled_at) "
            "VALUES (1, 1, 1, 4.0, 'OK', 'model', ?)",
            (_now(),),
        )
    mocker.patch(
        "steamtools.db.store._steam_review_counts",
        return_value={
            "total_reviews": 50,
            "total_positive": 40,
            "total_negative": 10,
            "review_score": 7,
            "review_score_desc": "Mostly Positive",
        },
    )
    result = runner.invoke(app, ["ai", "eval", "sync"])
    assert result.exit_code == 0


def test_eval_sync_no_data_for_appid(mocker):
    _app(1)
    _details(1)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO eval_results (appid, eval_type, eval_number, score, rationale, model, evaled_at) "
            "VALUES (1, 1, 1, 4.0, 'OK', 'model', ?)",
            (_now(),),
        )
    mocker.patch("steamtools.db.store._steam_review_counts", return_value=None)
    result = runner.invoke(app, ["ai", "eval", "sync"])
    assert result.exit_code == 0


# ── review-topics ─────────────────────────────────────────────────────────────


def test_review_topics_status_no_run():
    _app(1)
    result = runner.invoke(app, ["review-topics", "status", "1"])
    assert result.exit_code == 0
    assert "No topic runs yet" in result.output


def test_review_topics_status_with_run():
    _app(1)
    with get_connection() as conn:
        conn.execute("INSERT INTO app_reviews (review_id, appid, review, fetched_at) VALUES ('r1', 1, 'ok', ?)", (_now(),))
        conn.execute(
            "INSERT INTO review_topic_runs "
            "(appid, started_at, status, reviews_embedded, embedding_model, llm_model, hdbscan_params, chroma_collection) "
            "VALUES (1, ?, 'complete', 1, 'm', 'l', '{}', 'c')",
            (_now(),),
        )
    result = runner.invoke(app, ["review-topics", "status", "1"])
    assert result.exit_code == 0
    assert "Latest run" in result.output


def test_review_topics_classify_no_runs():
    _app(1)
    result = runner.invoke(app, ["review-topics", "classify", "1"])
    assert result.exit_code != 0
    assert "No topic runs" in result.output


def test_review_topics_discover(mocker):
    _app(1)
    mock_result = {
        "run_id": 1,
        "clusters_found": 2,
        "noise_count": 0,
        "topics": [{"category_name": "Fun", "review_count": 5}],
    }
    mocker.patch("steamtools.review_topics.pipeline.ReviewTopicPipeline.run_discovery", return_value=mock_result)
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = runner.invoke(app, ["review-topics", "discover", "1"])
    assert result.exit_code == 0


def test_review_topics_discover_error(mocker):
    _app(1)
    mocker.patch(
        "steamtools.review_topics.pipeline.ReviewTopicPipeline.run_discovery",
        return_value={"error": "No reviews found"},
    )
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = runner.invoke(app, ["review-topics", "discover", "1"])
    assert result.exit_code != 0


def test_review_topics_classify_with_run(mocker):
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
        return_value={"assigned": 3, "uncategorized": 1},
    )
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = runner.invoke(app, ["review-topics", "classify", "1"])
    assert result.exit_code == 0
    assert "assigned=3" in result.output


def test_review_topics_classify_error(mocker):
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
        return_value={"error": "No topics found"},
    )
    mocker.patch("steamtools.review_topics.embedder.SentenceTransformer")
    mocker.patch("steamtools.ai.gemini_client._client")
    mocker.patch("steamtools.vectordb.manager.chromadb.PersistentClient")
    result = runner.invoke(app, ["review-topics", "classify", "1"])
    assert result.exit_code != 0
