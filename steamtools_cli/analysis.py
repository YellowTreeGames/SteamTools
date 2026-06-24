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
    force: bool = typer.Option(False, help="Re-analyse already-processed reviews."),
    delay: float = typer.Option(4.0, help="Seconds between Gemini requests."),
    batch_size: int | None = typer.Option(None, help="Stop after processing this many reviews."),
    model: str = typer.Option("gemini-2.0-flash", help="Gemini model name."),
) -> None:
    """Run ABSA on all stored reviews for a game."""
    result = run_absa_pipeline(
        appid,
        StoDB(),
        AnalysisDB(),
        force=force,
        delay=delay,
        batch_size=batch_size,
        model=model,
    )
    print(f"processed={result['processed']} skipped={result['skipped']} failed={result['failed']}")


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
