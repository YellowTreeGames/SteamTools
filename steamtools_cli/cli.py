"""sto - command line interface for the SteamTools data pipeline."""

import typer

from steamtools.db import StoDB

app = typer.Typer(help="Command line interface for the SteamTools data pipeline.")


@app.command("info")
def info():
    """Show stats for the apps collection."""
    s = StoDB().status()
    print(f"Apps:            {s['total']}")
    print(f"  Last fetched:  {s['last_fetched'] or 'never'}")


@app.command("fetch")
def fetch(count: int | None = typer.Option(None, help="Fetch one page of this size instead of the full catalog.")):
    """Fetch the app list from Steam and upsert it into MongoDB."""
    n = StoDB().sync_app_list(count)
    print(f"Upserted {n} apps.")


@app.command("search")
def search(query: str = typer.Argument(..., help="Name substring to search for.")):
    """Search stored apps by name."""
    for a in StoDB().search_apps(query):
        print(f"{a['appid']}\t{a['name']}")


if __name__ == "__main__":
    app()
