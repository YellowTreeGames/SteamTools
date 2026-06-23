"""sto - command line interface for the SteamTools data pipeline."""

from collections.abc import Callable
from typing import Any, cast

import typer

from steamtools.db import DEFAULT_DETAILS_SLEEP, StoDB

app = typer.Typer(help="Command line interface for the SteamTools data pipeline.")


@app.command("info")
def info(
    apps: bool = typer.Option(False, "--app", help="Show stats for the apps table only."),
    details: bool = typer.Option(False, "--app-details", help="Show stats for the app-details table only."),
    reviews: bool = typer.Option(False, "--reviews", help="Show review stats."),
    appid: int | None = typer.Option(None, help="With --reviews, show summary for a specific game."),
):
    """Show pipeline status. Defaults to everything; use --app, --app-details, or --reviews to narrow."""
    if appid is not None and not reviews:
        raise typer.BadParameter("--appid requires --reviews.")

    show_all = not apps and not details and not reviews
    db = StoDB()

    if show_all or apps:
        s = db.app_stats()
        print(f"Apps:            {s['total']}")
        print(f"  With details:  {s['with_details']}")
        print(f"  Missing:       {s['total'] - s['with_details']}")
        print(f"  Last fetched:  {s['last_fetched'] or 'never'}")

    if show_all or details:
        s = db.app_details_stats()
        print(f"Details total:   {s['total']}")
        print(f"  Last fetched:  {s['last_fetched'] or 'never'}")

    if show_all or reviews:
        if appid is not None:
            summary = db.get_review_summary(appid)
            if summary is None:
                print(f"No review summary available for appid={appid}.")
                return
            _print_review_summary(appid, summary, fetched_at=summary.get("fetched_at", "unknown"))
        else:
            s = db.review_stats()
            print(f"Reviews:         {s['total_reviews']}")
            print(f"  Games:         {s['games_with_reviews']}")
            print(f"  Last fetched:  {s['last_fetched'] or 'never'}")


def _make_progress_logger(every: int, status_fn: Callable[[Any], str]) -> Callable:
    def log(i: int, total: int, aid: int, data: Any) -> None:
        if i % every == 0 or i == total:
            print(f"[{i}/{total}] appid={aid} {status_fn(data)}")

    return log


def _print_review_summary(appid: int, summary: dict, fetched_at: str | None = None) -> None:
    print(f"appid={appid}")
    print(f"  Score:    {summary.get('review_score_desc', 'N/A')} ({summary.get('review_score', '?')}/9)")
    print(f"  Total:    {summary.get('total_reviews', 0)}")
    print(f"  Positive: {summary.get('total_positive', 0)}")
    print(f"  Negative: {summary.get('total_negative', 0)}")
    if fetched_at is not None:
        print(f"  Fetched:  {fetched_at}")


@app.command("fetch")
def fetch(
    apps: bool = typer.Option(False, "--app", help="Fetch the apps list only."),
    details: bool = typer.Option(False, "--app-details", help="Fetch app details only."),
    reviews: bool = typer.Option(False, "--reviews", help="Fetch reviews for a game (requires --appid)."),
    count: int | None = typer.Option(None, help="Page size for --app; batch limit for --app-details."),
    sleep: float = typer.Option(DEFAULT_DETAILS_SLEEP, help="Delay between detail requests."),
    appid: int | None = typer.Option(None, help="Fetch a single explicit appid (--app-details or --reviews)."),
    force: bool = typer.Option(False, help="Re-fetch even if current (requires --appid)."),
    language: str = typer.Option("all", help="Review language filter (--reviews only)."),
):
    """Fetch data from Steam. Defaults to apps + details; use --reviews --appid ID for reviews."""
    show_all = not apps and not details and not reviews
    fetch_apps = show_all or apps
    fetch_details = show_all or details
    fetch_reviews = reviews

    if appid is not None and count is not None:
        raise typer.BadParameter("--appid and --count cannot be used together.")
    if force and appid is None:
        raise typer.BadParameter("--force requires --appid.")
    if appid is not None and not fetch_details and not fetch_reviews:
        raise typer.BadParameter("--appid requires --app-details or --reviews.")
    if fetch_reviews and appid is None:
        raise typer.BadParameter("--reviews requires --appid.")

    db = StoDB(details_sleep=sleep)

    if fetch_apps:
        n = db.sync_app_list(count if not show_all else None)
        print(f"Upserted {n} apps.")

    if fetch_details:
        if appid is not None:
            result = db.sync_app_details_one(appid, force=force)
            s = result["status"]
            if s == "game":
                print(f"appid={appid} status=game name={result['row']['name']}")
            elif s == "not_a_game":
                print(f"appid={appid} status=not_a_game detected_type={result['detected_type']!r}")
            else:
                print(f"appid={appid} status=already_current (use --force to re-fetch)")
        else:

            def _details_status(result: dict) -> str:
                s = result["status"]
                return f"dropped (type={result['detected_type']!r})" if s == "not_a_game" else s

            n = db.sync_app_details(limit=count, on_progress=_make_progress_logger(1, _details_status))
            print(f"Processed {n} apps.")

    if fetch_reviews:
        appid_int = cast(int, appid)
        result = db.sync_reviews(appid_int, force=force, language=language)
        if result["status"] == "already_current":
            print(f"appid={appid_int} status=already_current (use --force to re-fetch)")
        else:
            print(f"appid={appid_int} fetched={result['reviews_fetched']} reviews")
            _print_review_summary(appid_int, result["summary"] or {})


if __name__ == "__main__":
    app()
