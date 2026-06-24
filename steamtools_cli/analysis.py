"""Analysis pipeline CLI commands."""

import typer

from steamtools.analysis.pipeline import run_absa_pipeline
from steamtools.analysis.store import AnalysisDB
from steamtools.db.store import StoDB

analysis_app = typer.Typer(help="Analysis pipeline commands.")
absa_app = typer.Typer(help="Aspect-Based Sentiment Analysis.")
analysis_app.add_typer(absa_app, name="absa")


@absa_app.command("run")
def absa_run(
    appid: int = typer.Option(..., help="Steam appid to analyse."),
    force: bool = typer.Option(False, help="Wipe all existing ABSA data and rerun from discovery."),
    delay: float = typer.Option(4.0, help="Seconds between Gemini requests."),
    batch_size: int | None = typer.Option(None, help="Stop classify phase after processing this many reviews."),
    discovery_sample_size: int = typer.Option(50, help="Max reviews to sample during discovery (without replacement)."),
    discovery_batch_size: int = typer.Option(10, help="Reviews per batch sent to LLM during discovery."),
    model: str = typer.Option("gemini-3.1-flash-lite", help="Gemini model name."),
) -> None:
    """Run ABSA on all stored reviews for a game."""
    print(f"Running ABSA for appid={appid} model={model}")
    result = run_absa_pipeline(
        appid,
        StoDB(),
        AnalysisDB(),
        force=force,
        delay=delay,
        batch_size=batch_size,
        discovery_sample_size=discovery_sample_size,
        discovery_batch_size=discovery_batch_size,
        model=model,
        on_progress=print,
    )
    built = " (taxonomy rebuilt)" if result["taxonomy_built"] else ""
    print(f"\nDone{built} — processed={result['processed']} skipped={result['skipped']} failed={result['failed']}")


@absa_app.command("info")
def absa_info(
    appid: int = typer.Option(..., help="Steam appid to show analysis for."),
) -> None:
    """Show ABSA breakdown for a game by category and sentiment."""
    stats = AnalysisDB().absa_stats(appid)
    print(f"appid={appid}  reviews_processed={stats['reviews_processed']}")
    print()
    print("By category:")
    for row in stats["by_category"]:
        print(f"  {row['category']:<20} {row['count']}")
    print()
    print("By sentiment:")
    for row in stats["by_sentiment"]:
        print(f"  {row['sentiment']:<20} {row['count']}")
