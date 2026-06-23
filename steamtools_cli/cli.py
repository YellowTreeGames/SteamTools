"""sto - command line interface for the SteamTools data pipeline."""

from collections.abc import Callable
from typing import Any

import typer

from steamtools.db import DEFAULT_DETAILS_SLEEP, StoDB

app = typer.Typer(help="Command line interface for the SteamTools data pipeline.")
app_group = typer.Typer(help="Manage Steam applications.")
details_group = typer.Typer(help="Manage application details.")

app.add_typer(app_group, name="app")
app.add_typer(details_group, name="app-details")


def _make_progress_logger(every: int, status_fn: Callable[[Any], str]) -> Callable:
    def log(i: int, total: int, aid: int, data: Any) -> None:
        if i % every == 0 or i == total:
            print(f"[{i}/{total}] appid={aid} {status_fn(data)}")

    return log


@app.command("status")
def status():
    """Show combined status of apps and app-details tables."""
    s = StoDB().status()
    print(f"Apps:            {s['apps_total']}")
    print(f"  With details:  {s['apps_with_details']}")
    print(f"  Missing:       {s['apps_missing_details']}")
    print(f"  Last fetched:  {s['apps_last_fetched'] or 'never'}")
    print(f"Details total:   {s['details_total']}")
    print(f"  Last fetched:  {s['details_last_fetched'] or 'never'}")


@app_group.command("info")
def app_info():
    """Get high-level information about the apps table."""
    db = StoDB()
    s = db.app_stats()
    print(f"Total:          {s['total']}")
    print(f"With details:   {s['with_details']}")
    print(f"Missing details:{s['total'] - s['with_details']}")
    print(f"Last fetched:   {s['last_fetched'] or 'never'}")


@app_group.command("fetch")
def app_fetch(
    count: int | None = typer.Option(
        None, help="Fetch one page of this size from the last known appid, instead of a full refresh."
    ),
):
    """Fetch the master list of applications from Steam."""
    db = StoDB()
    n = db.sync_app_list(count)
    print(f"Upserted {n} apps.")


@details_group.command("info")
def app_details_info():
    """Get stats on the locally stored app details."""
    db = StoDB()
    s = db.app_details_stats()
    print(f"Total:        {s['total']}")
    print(f"Last fetched: {s['last_fetched'] or 'never'}")


@details_group.command("fetch")
def details_fetch(
    count: int | None = typer.Option(None, help="Max number of apps to fetch this run."),
    sleep: float = typer.Option(DEFAULT_DETAILS_SLEEP, help="Delay between requests."),
    appid: int | None = typer.Option(None, help="Fetch a single explicit appid instead of the pending batch."),
    force: bool = typer.Option(False, help="Re-fetch even if details are current (requires --appid)."),
):
    """Fetch deeper details for known applications."""
    if appid is not None and count is not None:
        raise typer.BadParameter("--appid and --count cannot be used together.")
    if force and appid is None:
        raise typer.BadParameter("--force requires --appid.")

    db = StoDB(details_sleep=sleep)

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

        n = db.sync_app_details(limit=count, on_progress=_make_progress_logger(50, _details_status))
        print(f"Processed {n} apps.")


if __name__ == "__main__":
    app()
