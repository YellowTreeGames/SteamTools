"""Analysis pipeline CLI commands."""

import typer
from rich.console import Console
from rich.text import Text

from steamtools.analysis.pipeline import run_absa_pipeline
from steamtools.analysis.store import AnalysisDB
from steamtools.db.store import StoDB

_console = Console()

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


_BAR_WIDTH = 20


def _sentiment_bar(pos: int, neg: int, mix: int) -> Text:
    total = pos + neg + mix
    bar = Text()
    if total == 0:
        bar.append("─" * _BAR_WIDTH, style="dim")
        return bar
    pos_w = round(pos / total * _BAR_WIDTH)
    neg_w = round(neg / total * _BAR_WIDTH)
    mix_w = _BAR_WIDTH - pos_w - neg_w
    bar.append("█" * pos_w, style="green")
    bar.append("█" * mix_w, style="yellow")
    bar.append("█" * neg_w, style="red")
    return bar


@absa_app.command("info")
def absa_info(
    appid: int = typer.Option(..., help="Steam appid to show analysis for."),
) -> None:
    """Show ABSA feature breakdown for a game, grouped by category."""
    db = AnalysisDB()
    stats = db.absa_stats(appid)
    breakdown = db.get_feature_breakdown(appid)

    total_aspects = sum(r["count"] for r in stats["by_sentiment"])
    _console.print(f"appid={appid}  reviews_processed={stats['reviews_processed']}  aspects={total_aspects}\n")

    for cat in breakdown:
        score: int = cat["score"]
        score_str = f"+{score}" if score > 0 else str(score)
        score_style = "green" if score > 0 else "red" if score < 0 else "dim"
        header = Text()
        header.append(str(cat["category"]), style="bold cyan")
        header.append(f"  ({cat['total']} mentions,  score ", style="dim")
        header.append(score_str, style=score_style)
        header.append(")", style="dim")
        _console.print(header)
        for feat in cat["features"]:
            pos: int = feat["positive"]
            neg: int = feat["negative"]
            mix: int = feat["mixed"]
            counts = Text()
            counts.append(f"+{pos}", style="green")
            counts.append(" ")
            counts.append(f"-{neg}", style="red")
            if mix:
                counts.append(" ")
                counts.append(f"~{mix}", style="yellow")
            name = Text(f"  {feat['feature']:<33}", style="white")
            line = Text.assemble(name, " ", _sentiment_bar(pos, neg, mix), "  ", counts)
            _console.print(line)
        _console.print()
