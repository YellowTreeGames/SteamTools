"""Tests for steamtools.ai.eval."""

from datetime import UTC

import steamtools.ai.eval as ai_eval
from steamtools.db.connection import get_connection
from steamtools.db.store import StoDB


def _now_iso():
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _setup_game(appid=1, short_description="A cool game."):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, "Test Game", _now_iso()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_details "
            "(appid, type, name, is_free, coming_soon, release_date, short_description, fetched_at) "
            "VALUES (?, 'game', 'Test Game', 0, 0, '2020-01-01', ?, ?)",
            (appid, short_description, _now_iso()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_review_counts "
            "(appid, total_reviews, total_positive, total_negative, review_score, review_score_desc, fetched_at) "
            "VALUES (?, 200, 160, 40, 8, 'Very Positive', ?)",
            (appid, _now_iso()),
        )


def test_run_evals_success(mocker):
    _setup_game()
    mock_eval = mocker.patch(
        "steamtools.ai.eval.gemini_client.evaluate",
        return_value={"score": 3.5, "rationale": "Good."},
    )
    db = StoDB()
    ai_eval.run_evals(db, n=1, appids=[], eval_type_name="Appeal")
    mock_eval.assert_called_once()


def test_run_evals_no_games_with_details(mocker, capsys):
    _setup_game()
    db = StoDB()
    # Fill up all eval slots first
    for _ in range(5):
        db.save_eval_result(1, 1, 4.0, "OK", "m")
    ai_eval.run_evals(db, n=1, appids=[], eval_type_name="Appeal")
    captured = capsys.readouterr()
    assert "No games pending" in captured.out


def test_run_evals_no_games_no_details(capsys):
    db = StoDB()
    ai_eval.run_evals(db, n=1, appids=[], eval_type_name="Appeal")
    captured = capsys.readouterr()
    assert "app-details fetch" in captured.out


def test_run_evals_skips_on_value_error(mocker):
    _setup_game()
    mocker.patch(
        "steamtools.ai.eval.gemini_client.evaluate",
        side_effect=ValueError("bad response"),
    )
    db = StoDB()
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        ai_eval.run_evals(db, n=1, appids=[], eval_type_name="Appeal")
    assert any("Skipping" in str(warning.message) for warning in w)


def test_plot_correlation_no_data(capsys):
    db = StoDB()
    ai_eval.plot_correlation(db, "Appeal")
    captured = capsys.readouterr()
    assert "No eval results" in captured.out


def test_plot_correlation_with_data(mocker):
    _setup_game()
    db = StoDB()
    db.save_eval_result(1, 1, 4.0, "Good", "m")

    mock_show = mocker.patch("steamtools.ai.eval.plt.show")
    mocker.patch("steamtools.ai.eval.plt.figure")
    mocker.patch("steamtools.ai.eval.plt.scatter")
    mocker.patch("steamtools.ai.eval.plt.plot")
    mocker.patch("steamtools.ai.eval.plt.xlabel")
    mocker.patch("steamtools.ai.eval.plt.ylabel")
    mocker.patch("steamtools.ai.eval.plt.title")
    mocker.patch("steamtools.ai.eval.plt.tight_layout")

    ai_eval.plot_correlation(db, "Appeal")
    mock_show.assert_called_once()
