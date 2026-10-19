"""sto - command line interface for the SteamTools data pipeline."""

from collections.abc import Callable
from typing import Any

import typer

from steamtools.db import DEFAULT_DETAILS_SLEEP, StoDB
from steamtools_cli.analysis import analysis_app
from steamtools_cli.reviews import reviews_app

app = typer.Typer(help="Command line interface for the SteamTools data pipeline.")
app.add_typer(analysis_app, name="analysis")
app.add_typer(reviews_app, name="reviews")


@app.command("info")
def info(
    apps: bool = typer.Option(False, "--app", help="Show stats for the apps table only."),
    details: bool = typer.Option(False, "--app-details", help="Show stats for the app-details table only."),
):
    """Show pipeline status. Defaults to everything; use --app or --app-details to narrow."""
    show_all = not apps and not details
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

    if show_all:
        s = db.review_stats()
        print(f"Reviews:         {s['total_reviews']}")
        print(f"  Games:         {s['games_with_reviews']}")
        print(f"  Last fetched:  {s['last_fetched'] or 'never'}")


def _make_progress_logger(every: int, status_fn: Callable[[Any], str]) -> Callable:
    def log(i: int, total: int, aid: int, data: Any) -> None:
        if i % every == 0 or i == total:
            print(f"[{i}/{total}] appid={aid} {status_fn(data)}")

    return log


@app.command("fetch")
def fetch(
    apps: bool = typer.Option(False, "--app", help="Fetch the apps list only."),
    details: bool = typer.Option(False, "--app-details", help="Fetch app details only."),
    count: int | None = typer.Option(None, help="Page size for --app; batch limit for --app-details."),
    sleep: float = typer.Option(DEFAULT_DETAILS_SLEEP, help="Delay between detail requests."),
    appid: int | None = typer.Option(None, help="Fetch a single explicit appid (--app-details)."),
    force: bool = typer.Option(False, help="Re-fetch even if current (requires --appid)."),
):
    """Fetch data from Steam. Defaults to apps + details."""
    show_all = not apps and not details
    fetch_apps = show_all or apps
    fetch_details = show_all or details

    if appid is not None and count is not None:
        raise typer.BadParameter("--appid and --count cannot be used together.")
    if force and appid is None:
        raise typer.BadParameter("--force requires --appid.")
    if appid is not None and not fetch_details:
        raise typer.BadParameter("--appid requires --app-details.")

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


if __name__ == "__main__":
    app()
