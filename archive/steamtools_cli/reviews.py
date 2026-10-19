"""Review pipeline CLI commands."""

import typer

from steamtools.db.store import StoDB

reviews_app = typer.Typer(help="Review fetch and info commands.")


@reviews_app.command("fetch")
def reviews_fetch(
    appid: int = typer.Option(..., help="Steam appid to fetch reviews for."),
    force: bool = typer.Option(False, help="Re-fetch even if current."),
    language: str = typer.Option("all", help="Review language filter."),
    filter: str = typer.Option("recent", help="Steam review filter (recent or all)."),  # noqa: A002
) -> None:
    """Fetch and store all reviews for a game."""
    result = StoDB().sync_reviews(appid, force=force, language=language, filter=filter)
    if result["status"] == "already_current":
        print(f"appid={appid} status=already_current (use --force to re-fetch)")
    else:
        print(f"appid={appid} fetched={result['reviews_fetched']} reviews")
        _print_review_summary(appid, result["summary"] or {})


@reviews_app.command("info")
def reviews_info(
    appid: int | None = typer.Option(None, help="Show summary for a specific game."),
) -> None:
    """Show stored review stats. With --appid, shows that game's summary."""
    db = StoDB()
    if appid is not None:
        summary = db.get_review_summary(appid)
        if summary is None:
            print(f"No review summary available for appid={appid}.")
            return
        _print_review_summary(appid, summary, fetched_at=summary.get("fetched_at"))
    else:
        s = db.review_stats()
        print(f"Reviews:         {s['total_reviews']}")
        print(f"  Games:         {s['games_with_reviews']}")
        print(f"  Last fetched:  {s['last_fetched'] or 'never'}")


def _print_review_summary(appid: int, summary: dict, fetched_at: str | None = None) -> None:
    print(f"appid={appid}")
    print(f"  Score:    {summary.get('review_score_desc', 'N/A')} ({summary.get('review_score', '?')}/9)")
    print(f"  Total:    {summary.get('total_reviews', 0)}")
    print(f"  Positive: {summary.get('total_positive', 0)}")
    print(f"  Negative: {summary.get('total_negative', 0)}")
    if fetched_at is not None:
        print(f"  Fetched:  {fetched_at}")
