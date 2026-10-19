"""stdio MCP server exposing SteamTools data pipeline tools.

Run via: uv run python -m steamtools_mcp.server
"""

from mcp.server.fastmcp import FastMCP

from steamtools.db import StoDB

mcp = FastMCP("steamtools")


@mcp.tool()
def status() -> dict:
    """Get status of the apps collection: {total, last_fetched}."""
    return StoDB().status()


@mcp.tool()
def search_games(query: str) -> list[dict]:
    """Search games by name substring. Returns list of {appid, name}."""
    return StoDB().search_apps(query)


@mcp.tool()
def fetch_app_list(count: int | None = None) -> dict:
    """Fetch the master list of apps from Steam and upsert into the apps collection.

    count=None does a full catalog refresh; count=N fetches one page of that size.
    Returns {"upserted": int}.
    """
    return {"upserted": StoDB().sync_app_list(count)}


if __name__ == "__main__":
    mcp.run()
