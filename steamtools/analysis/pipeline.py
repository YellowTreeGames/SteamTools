"""Steam-aware ABSA pipeline coordinator."""

import random
import time
from collections.abc import Callable

from google import genai

from general.analysis.absa import analyze_review, canonicalize_taxonomy, discover_batch
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
    discovery_sample_size: int = 50,
    discovery_batch_size: int = 10,
    model: str = "gemini-3.1-flash-lite",
    on_progress: Callable[[str], None] | None = None,
) -> dict:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    if force:
        db_analysis.wipe_game_absa(appid)

    taxonomy_row = db_analysis.get_taxonomy(appid)
    taxonomy_built = False

    if taxonomy_row is None or taxonomy_row["status"] != "ready":
        taxonomy_built = True
        all_reviews = db_steam.get_reviews(appid)
        reviewable = [r for r in all_reviews if r.get("review")]

        if not reviewable:
            raise ValueError(f"No reviews with text found for appid={appid}. Fetch reviews first.")

        sample = random.sample(reviewable, min(discovery_sample_size, len(reviewable)))  # nosec B311
        accumulated: dict[str, list[str]] = {}
        early_stopped = False
        reviews_sampled = 0

        db_analysis.upsert_taxonomy(appid, "discovering", discovery_sample_size, model)

        total_batches = (len(sample) + discovery_batch_size - 1) // discovery_batch_size
        if on_progress:
            on_progress(f"Discovery: {len(sample)} reviews in {total_batches} batch(es)")

        for batch_start in range(0, len(sample), discovery_batch_size):
            batch = sample[batch_start : batch_start + discovery_batch_size]
            batch_texts = [r["review"][:1500] for r in batch]
            batch_num = batch_start // discovery_batch_size + 1

            new_pairs, done = discover_batch(batch_texts, accumulated, client, model)
            for pair in new_pairs:
                if pair.feature not in accumulated.get(pair.category, []):
                    accumulated.setdefault(pair.category, []).append(pair.feature)
            reviews_sampled += len(batch_texts)

            if on_progress:
                on_progress(
                    f"  [{batch_num}/{total_batches}] {len(batch_texts)} reviews: +{len(new_pairs)} pairs, complete={done}"
                )

            if done:
                early_stopped = True
                break
            time.sleep(delay)

        if on_progress:
            on_progress("Canonicalize: building canonical taxonomy...")
        canonical = canonicalize_taxonomy(accumulated, client, model)
        db_analysis.save_taxonomy_data(
            appid,
            [c.model_dump() for c in canonical],
            discovery_sample_size=discovery_sample_size,
            discovery_reviews_sampled=reviews_sampled,
            early_stopped=early_stopped,
            model=model,
        )
        feature_count = sum(len(c.features) for c in canonical)
        if on_progress:
            on_progress(f"  ready: {len(canonical)} categories, {feature_count} features")

    taxonomy = db_analysis.get_taxonomy_for_classify(appid)
    reviews = db_steam.get_reviews(appid)
    already_processed = db_analysis.get_processed_review_ids(appid)

    processed = 0
    skipped = 0
    failed = 0
    total = len(reviews)

    if on_progress:
        on_progress(f"Classify: {total} reviews total")

    for i, review in enumerate(reviews, 1):
        if batch_size is not None and processed + failed >= batch_size:
            break

        review_id: int = review["recommendationid"]
        text: str = review["review"] or ""

        if review_id in already_processed:
            skipped += 1
            continue

        try:
            aspects = analyze_review(text, model, client, taxonomy=taxonomy)
            db_analysis.save_absa_result(review_id, appid, [a.model_dump() for a in aspects], model)
            processed += 1
            if on_progress:
                on_progress(f"  [{i}/{total}] {review_id}: ok ({len(aspects)} aspects)")
        except Exception as e:
            failed += 1
            if on_progress:
                on_progress(f"  [{i}/{total}] {review_id}: FAILED: {e}")

        time.sleep(delay)

    return {"processed": processed, "skipped": skipped, "failed": failed, "taxonomy_built": taxonomy_built}
