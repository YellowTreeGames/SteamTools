"""Orchestration for LLM-based game evaluations."""

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from steamtools.ai import gemini_client
from steamtools.config import GEMINI_MODEL, MAX_SCORES
from steamtools.db import StoDB


def run_evals(db: StoDB, n: int, appids: list[int], eval_type_name: str, fill: bool = False, min_reviews: int = 1) -> None:
    eval_type = db.get_eval_type(eval_type_name)
    eval_type_id = eval_type["id"]
    template_path = Path(__file__).parent.parent / "prompts" / eval_type["template_file"]

    games = db.get_pending_eval_games(
        eval_type_id, list(appids), n=None if fill else n, fill=fill, max_scores=MAX_SCORES, min_reviews=min_reviews
    )

    if not games:
        if not db.has_app_details():
            print("No app details in DB. Run `sto app-details fetch` first.")
        else:
            print("No games pending evaluation.")
        return

    if fill:
        print(f"Fill mode: {len(games)} games pending across all evals.")

    for game in games:
        appid = game["appid"]
        name = game["name"]
        desc = game["short_description"]

        try:
            result = gemini_client.evaluate(name, desc, template_path, GEMINI_MODEL)
        except ValueError as exc:
            warnings.warn(f"Skipping appid={appid} ({name}): {exc}")
            continue

        eval_number = db.save_eval_result(appid, eval_type_id, result["score"], result["rationale"], GEMINI_MODEL)
        print(f"{appid} | {name} | score={result['score']} | run {eval_number}/{MAX_SCORES}")


def plot_correlation(db: StoDB, eval_type_name: str) -> None:
    eval_type = db.get_eval_type(eval_type_name)
    rows = db.get_eval_correlation_data(eval_type["id"])

    if not rows:
        print("No eval results with review counts found.")
        return

    scores = np.array([r["avg_score"] for r in rows])
    reviews = np.array([r["total_reviews"] for r in rows])

    slope, intercept, r_value, _p, _se = stats.linregress(scores, reviews)
    line_x = np.linspace(scores.min(), scores.max(), 100)
    line_y = slope * line_x + intercept

    plt.figure(figsize=(10, 6))
    plt.scatter(scores, reviews, alpha=0.5, s=20)
    plt.plot(line_x, line_y, color="red", linewidth=1.5)
    plt.xlabel(f"Average {eval_type_name} Score")
    plt.ylabel("Total Reviews")
    plt.title(f"{eval_type_name} Score vs. Review Count  (r={r_value:.3f}, n={len(rows)})")
    plt.tight_layout()
    plt.show()
