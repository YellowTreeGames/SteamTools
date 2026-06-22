"""sto - command line interface for the SteamTools data pipeline."""

from typing import List, Optional

import typer

from steamtools.ai import eval as ai_eval
from steamtools.db import DEFAULT_DETAILS_SLEEP, DEFAULT_REVIEWS_SLEEP, StoDB

app = typer.Typer(help="Command line interface for the SteamTools data pipeline.")
app_group = typer.Typer(help="Manage Steam applications.")
details_group = typer.Typer(help="Manage application details.")
reviews_group = typer.Typer(help="Manage app review counts.")
review_topics_group = typer.Typer(help="Review topic discovery and classification.")
ai_group = typer.Typer(help="AI-powered analysis commands.")
eval_group = typer.Typer(help="Evaluation commands.")

app.add_typer(app_group, name="app")
app.add_typer(details_group, name="app-details")
app.add_typer(reviews_group, name="app-reviews")
app.add_typer(review_topics_group, name="review-topics")
app.add_typer(ai_group, name="ai")
ai_group.add_typer(eval_group, name="eval")


@app_group.command("info")
def app_info():
    """Get high-level information about fetched apps."""
    db = StoDB()
    s = db.app_stats()
    print(f"Apps: {s['total']}")
    print(f"With details: {s['with_details']}")
    print(f"Missing details: {s['total'] - s['with_details']}")
    print(f"Last fetched: {s['last_fetched'] or 'never'}")


@app_group.command("search")
def app_search(query: str = typer.Argument(..., help="Substring to search for in game names.")):
    """Search for games by name substring."""
    db = StoDB()
    results = db.search_apps(query)
    if not results:
        print(f"No games found matching '{query}'.")
        return
    for r in results:
        has = "yes" if r["has_details"] else "no"
        print(f"{r['appid']}\t{r['name']}\t(details: {has})")


@app_group.command("fetch")
def app_fetch(
    count: Optional[int] = typer.Option(
        None, help="Fetch one page of this size from the last known appid, instead of a full refresh."
    )
):
    """Fetch the master list of applications."""
    db = StoDB()
    n = db.sync_app_list(count)
    print(f"Upserted {n} apps.")


@details_group.command("info")
def app_details_info():
    """Get stats on the locally stored app details."""
    db = StoDB()
    s = db.app_details_stats()
    print(f"App details: {s['total']}")
    print(f"Last appid: {s['last_appid']}")
    print(f"Last fetched: {s['last_fetched'] or 'never'}")


@details_group.command("fetch")
def details_fetch(
    count: Optional[int] = typer.Option(None, help="Max number of apps to fetch this run."),
    sleep: float = typer.Option(DEFAULT_DETAILS_SLEEP, help="Delay between requests."),
    appid: Optional[int] = typer.Option(None, help="Fetch a single explicit appid instead of the pending batch."),
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
        status = result["status"]
        if status == "game":
            print(f"appid={appid} status=game name={result['row']['name']}")
        elif status == "not_a_game":
            print(f"appid={appid} status=not_a_game detected_type={result['detected_type']!r}")
        else:
            print(f"appid={appid} status=already_current (use --force to re-fetch)")
    else:
        def log(i: int, total: int, aid: int, result: dict) -> None:
            if i % 50 == 0 or i == total:
                s = result["status"]
                if s == "not_a_game":
                    s = f"dropped (type={result['detected_type']!r})"
                print(f"[{i}/{total}] appid={aid} {s}")

        n = db.sync_app_details(limit=count, on_progress=log)
        print(f"Processed {n} apps.")


@reviews_group.command("info")
def app_reviews_info():
    """Get stats on locally stored review counts."""
    db = StoDB()
    s = db.review_stats()
    print(f"Review counts: {s['total']}")
    print(f"Last fetched: {s['last_fetched'] or 'never'}")


@reviews_group.command("fetch")
def reviews_fetch(
    count: Optional[int] = typer.Option(None, help="Max number of apps to fetch this run."),
    sleep: float = typer.Option(DEFAULT_REVIEWS_SLEEP, help="Delay between requests."),
):
    """Fetch review counts for stale or missing apps."""
    db = StoDB(reviews_sleep=sleep)

    def log(i: int, total: int, aid: int, data: dict | None) -> None:
        if i % 50 == 0 or i == total:
            status = f"total_reviews={data['total_reviews']}" if data else "no_data"
            print(f"[{i}/{total}] appid={aid} {status}")

    n = db.sync_review_counts(limit=count, on_progress=log)
    print(f"Synced {n} review counts.")


@eval_group.command("short-description")
def eval_short_description(
    n: int = typer.Option(50, "-n", help="Number of games to sample for evaluation."),
    appid: List[int] = typer.Option([], help="Score a specific appid instead of sampling."),
    eval_type: str = typer.Option("Appeal", "--eval-type", help="Name of eval type (see eval_types table)."),
    show_eval: bool = typer.Option(False, "--eval", help="Show scatter plot of score vs. review count."),
    fill: bool = typer.Option(False, "--fill", help="Evaluate all games below MAX_SCORES, ignoring -n."),
    min_reviews: int = typer.Option(1, "--min-reviews", help="Minimum total reviews required to be a candidate."),
):
    """Score game short descriptions with an LLM, or visualize score vs. review count."""
    db = StoDB()
    if show_eval:
        ai_eval.plot_correlation(db, eval_type)
    else:
        ai_eval.run_evals(db, n, appid, eval_type, fill=fill, min_reviews=min_reviews)


@eval_group.command("sync")
def eval_sync(
    sleep: float = typer.Option(DEFAULT_REVIEWS_SLEEP, help="Delay between requests."),
):
    """Refresh review counts for evaluated games that are stale."""
    db = StoDB(reviews_sleep=sleep)
    appids = db.get_stale_review_appids_for_evals()
    if not appids:
        print("All evaluated games have fresh review counts.")
        return
    print(f"{len(appids)} evaluated games need review count refresh.")

    def log(i: int, total: int, aid: int, data: dict | None) -> None:
        if i % 25 == 0 or i == total:
            status = f"total_reviews={data['total_reviews']}" if data else "no data"
            print(f"[{i}/{total}] appid={aid} {status}")

    synced = db.sync_review_counts(appids=appids, on_progress=log)
    print(f"Synced {synced} review counts.")


@reviews_group.command("fetch-text")
def reviews_fetch_text(
    appid: int = typer.Argument(..., help="Steam appid to fetch reviews for."),
    max: int = typer.Option(10000, "--max", help="Maximum number of reviews to fetch."),
    filter: str = typer.Option("all", "--filter", help="Review filter: all, recent, or funny."),
    sleep: float = typer.Option(1.0, "--sleep", help="Delay in seconds between page requests."),
):
    """Fetch review texts for a game and store them locally."""
    db = StoDB()

    def log(fetched: int, total: int) -> None:
        if fetched % 500 == 0 or fetched >= total:
            print(f"Fetched {fetched} reviews...")

    result = db.fetch_reviews(appid, max_reviews=max, filter_type=filter, sleep=sleep, on_progress=log)
    print(f"Done. session_id={result['session_id']} reviews_fetched={result['reviews_fetched']}")


@review_topics_group.command("discover")
def review_topics_discover(
    appid: int = typer.Argument(..., help="Steam appid to run topic discovery for."),
    min_cluster_size: int = typer.Option(15, "--min-cluster-size", help="Minimum reviews per cluster."),
):
    """Embed reviews, cluster with HDBSCAN, and name clusters with Gemini."""
    from steamtools.vectordb import VectorManager
    from steamtools.review_topics.embedder import ReviewEmbedder
    from steamtools.review_topics.clusterer import ReviewClusterer
    from steamtools.review_topics.labeler import ClusterLabeler
    from steamtools.review_topics.pipeline import ReviewTopicPipeline

    db = StoDB()
    vm = VectorManager()
    embedder = ReviewEmbedder()
    clusterer = ReviewClusterer(min_cluster_size=min_cluster_size)
    labeler = ClusterLabeler()
    pipeline = ReviewTopicPipeline(db, vm, embedder, clusterer, labeler)

    print(f"Running topic discovery for appid={appid}...")
    result = pipeline.run_discovery(appid, min_cluster_size=min_cluster_size)

    if "error" in result:
        print(f"Error: {result['error']}")
        raise typer.Exit(1)

    print(f"run_id={result['run_id']} clusters={result['clusters_found']} noise={result['noise_count']}")
    for t in result["topics"]:
        print(f"  [{t['review_count']:>5} reviews] {t['category_name']}")


@review_topics_group.command("classify")
def review_topics_classify(
    appid: int = typer.Argument(..., help="Steam appid to classify reviews for."),
    run_id: Optional[int] = typer.Option(None, "--run-id", help="Topic run id (defaults to latest)."),
    threshold: float = typer.Option(0.85, "--threshold", help="Cosine similarity threshold for assignment."),
):
    """Classify reviews against discovered topics."""
    from steamtools.vectordb import VectorManager
    from steamtools.review_topics.embedder import ReviewEmbedder
    from steamtools.review_topics.clusterer import ReviewClusterer
    from steamtools.review_topics.labeler import ClusterLabeler
    from steamtools.review_topics.pipeline import ReviewTopicPipeline

    db = StoDB()
    runs = db.get_topic_runs(appid)
    if not runs:
        print(f"No topic runs found for appid={appid}. Run discover first.")
        raise typer.Exit(1)

    resolved_run_id = run_id if run_id is not None else runs[0]["id"]
    print(f"Classifying reviews for appid={appid} run_id={resolved_run_id}...")

    vm = VectorManager()
    embedder = ReviewEmbedder()
    clusterer = ReviewClusterer()
    labeler = ClusterLabeler()
    pipeline = ReviewTopicPipeline(db, vm, embedder, clusterer, labeler)

    result = pipeline.classify_reviews(appid, resolved_run_id, threshold=threshold)
    if "error" in result:
        print(f"Error: {result['error']}")
        raise typer.Exit(1)

    print(f"assigned={result['assigned']} uncategorized={result['uncategorized']}")


@review_topics_group.command("status")
def review_topics_status(
    appid: int = typer.Argument(..., help="Steam appid to show topic status for."),
):
    """Show topic discovery status for a game."""
    db = StoDB()
    status = db.get_review_topics_status(appid)

    print(f"Reviews stored: {status['review_count']}")
    print(f"Uncategorized:  {status['uncategorized_count']}")

    if status["latest_run"]:
        r = status["latest_run"]
        print(f"\nLatest run: id={r['id']} status={r['status']} clusters={r['clusters_found']} noise={r['noise_count']}")
        print(f"  started={r['started_at']}  completed={r['completed_at']}")
        if status["topics"]:
            print("\nTopics:")
            for t in status["topics"]:
                print(f"  [{t['review_count']:>5}] {t['category_name']} — {t['description']}")
    else:
        print("\nNo topic runs yet. Run `sto review-topics discover <appid>` first.")


if __name__ == "__main__":
    app()
