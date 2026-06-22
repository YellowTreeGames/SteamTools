"""stdio MCP server exposing search_games and get_app_details tools.

Run via: uv run python -m steamtools_mcp.server
"""

from mcp.server.fastmcp import FastMCP

from steamtools.db import DEFAULT_DETAILS_SLEEP, StoDB

mcp = FastMCP("steamtools")


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
def get_game(appid: int) -> dict | None:
    """Get a combined view of app, app details, and review counts for a game.

    Returns a single dict merging fields from apps, app_details, and app_review_counts.
    Returns None if the appid is not in the apps table.
    All values are from the local cache — call get_app_details first to trigger a
    fresh fetch if details are missing or stale.
    """
    return StoDB().get_game_view(appid)


@mcp.tool()
def fetch_review_texts(appid: int, max_reviews: int = 10000, filter_type: str = "all") -> dict:
    """Fetch review texts for a game from Steam and store them locally.

    Returns {"session_id": int, "reviews_fetched": int}.
    filter_type: "all", "recent", or "funny".
    """
    return StoDB().fetch_reviews(appid, max_reviews=max_reviews, filter_type=filter_type)


@mcp.tool()
def discover_review_topics(appid: int, min_cluster_size: int = 15) -> dict:
    """Run topic discovery on locally stored reviews for a game.

    Embeds reviews, clusters with HDBSCAN, names clusters with Gemini.
    Returns {"run_id": int, "clusters_found": int, "noise_count": int, "topics": [...]}.
    Requires reviews to be fetched first via fetch_review_texts.
    """
    from steamtools.vectordb import VectorManager
    from steamtools.review_topics.embedder import ReviewEmbedder
    from steamtools.review_topics.clusterer import ReviewClusterer
    from steamtools.review_topics.labeler import ClusterLabeler
    from steamtools.review_topics.pipeline import ReviewTopicPipeline

    db = StoDB()
    vm = VectorManager()
    pipeline = ReviewTopicPipeline(db, vm, ReviewEmbedder(), ReviewClusterer(min_cluster_size), ClusterLabeler())
    return pipeline.run_discovery(appid, min_cluster_size=min_cluster_size)


@mcp.tool()
def classify_review_topics(appid: int, run_id: int | None = None, threshold: float = 0.85) -> dict:
    """Classify reviews against discovered topics for a game.

    Uses the latest run for the appid if run_id is omitted.
    Returns {"assigned": int, "uncategorized": int}.
    """
    from steamtools.vectordb import VectorManager
    from steamtools.review_topics.embedder import ReviewEmbedder
    from steamtools.review_topics.clusterer import ReviewClusterer
    from steamtools.review_topics.labeler import ClusterLabeler
    from steamtools.review_topics.pipeline import ReviewTopicPipeline

    db = StoDB()
    runs = db.get_topic_runs(appid)
    if not runs:
        return {"error": f"No topic runs found for appid={appid}."}
    resolved_run_id = run_id if run_id is not None else runs[0]["id"]

    vm = VectorManager()
    pipeline = ReviewTopicPipeline(db, vm, ReviewEmbedder(), ReviewClusterer(), ClusterLabeler())
    return pipeline.classify_reviews(appid, resolved_run_id, threshold=threshold)


@mcp.tool()
def get_review_topics_status(appid: int) -> dict:
    """Get topic discovery status for a game.

    Returns review count, latest run info, topics list, and uncategorized count.
    """
    return StoDB().get_review_topics_status(appid)


if __name__ == "__main__":
    mcp.run()
