"""Steam-aware ABSA pipeline coordinator."""

import time

from google import genai

from general.analysis.absa import analyze_review
from steamtools import config
from steamtools.analysis.store import AnalysisDB
from steamtools.db.store import StoDB


def run_absa_pipeline(
    appid: int,
    db_steam: StoDB,
    db_analysis: AnalysisDB,
    *,
    force: bool = False,
    delay: float = 4.0,
    batch_size: int | None = None,
    model: str = "gemini-2.0-flash",
) -> dict:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    reviews = db_steam.get_reviews(appid)
    already_processed = db_analysis.get_processed_review_ids(appid)

    processed = 0
    skipped = 0
    failed = 0

    for review in reviews:
        if batch_size is not None and processed + failed >= batch_size:
            break

        review_id: int = review["recommendationid"]
        text: str = review["review"] or ""

        if review_id in already_processed:
            if force:
                db_analysis.delete_absa_result(review_id, appid)
            else:
                skipped += 1
                continue

        aspects = analyze_review(text, model, client)
        if aspects is None:
            failed += 1
        else:
            db_analysis.save_absa_result(review_id, appid, [a.model_dump() for a in aspects], model)
            processed += 1

        time.sleep(delay)

    return {"processed": processed, "skipped": skipped, "failed": failed}
