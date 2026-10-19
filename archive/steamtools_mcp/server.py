"""stdio MCP server exposing SteamTools data pipeline tools.

Run via: uv run python -m steamtools_mcp.server
"""

from mcp.server.fastmcp import FastMCP

from steamtools.analysis.pipeline import run_absa_pipeline
from steamtools.analysis.store import AnalysisDB
from steamtools.db import DEFAULT_DETAILS_SLEEP, StoDB

mcp = FastMCP("steamtools")


@mcp.tool()
def status() -> dict:
    """Get combined status of apps and app-details tables.

    Returns apps_total, apps_with_details, apps_missing_details,
    apps_last_fetched, details_total, details_last_fetched.
    """
    return StoDB().status()


@mcp.tool()
def search_games(query: str) -> list[dict]:
    """Search games by name substring. Returns list of {appid, name, has_details}."""
    return StoDB().search_apps(query)


@mcp.tool()
def get_app_details(appid: int, force: bool = False) -> dict:
    """Get app details for a game by appid.

    Returns cached row immediately if present and current (force=False). Otherwise
    fetches from Steam, upserts, and returns it. If the appid is not a game,
    returns {status: "not_a_game"} and removes it from the apps table.
    """
    return StoDB(details_sleep=DEFAULT_DETAILS_SLEEP).sync_app_details_one(appid, force=force)


@mcp.tool()
def fetch_app_list(count: int | None = None) -> dict:
    """Fetch the master list of apps from Steam and upsert into the apps table.

    count=None does a full catalog refresh; count=N fetches one page of that size.
    Returns {"upserted": int}.
    """
    n = StoDB().sync_app_list(count)
    return {"upserted": n}


@mcp.tool()
def fetch_app_details(count: int | None = None) -> dict:
    """Fetch details for all apps that are missing or stale (>30 days).

    count limits the number of apps processed in this run.
    Returns {"processed": int}.
    """
    n = StoDB().sync_app_details(limit=count)
    return {"processed": n}


@mcp.tool()
def fetch_reviews(appid: int, force: bool = False, language: str = "all") -> dict:
    """Fetch and store all reviews for a game by appid.

    Paginates through Steam's review API and upserts both the aggregate summary
    and individual review rows. Skips the fetch if the summary is <7 days old
    unless force=True.

    Returns {"status", "summary", "reviews_fetched"}.
    """
    return StoDB().sync_reviews(appid, force=force, language=language)


@mcp.tool()
def get_review_summary(appid: int) -> dict | None:
    """Get the stored review summary for a game by appid.

    Returns the DB row if present, or None if reviews have not been fetched yet.
    To refresh stale data, call fetch_reviews first.
    """
    return StoDB().get_review_summary(appid)


@mcp.tool()
def run_absa(appid: int, force: bool = False, delay: float = 4.0) -> dict:
    """Run ABSA on all stored reviews for a game.

    Returns {"processed": int, "skipped": int, "failed": int}.
    """
    return run_absa_pipeline(appid, StoDB(), AnalysisDB(), force=force, delay=delay)


@mcp.tool()
def get_absa_results(appid: int, category: str | None = None, sentiment: str | None = None) -> list[dict]:
    """Get ABSA aspect rows for a game, optionally filtered by category and/or sentiment."""
    return AnalysisDB().get_absa_aspects(appid, category=category, sentiment=sentiment)


if __name__ == "__main__":
    mcp.run()
