"""Pure ABSA engine — no Steam, DB, or project-specific imports."""

from pathlib import Path

from google import genai
from google.genai import types as genai_types
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

SEED_CATEGORIES: list[str] = ["UI_UX", "Gameplay", "Narrative", "Audio", "Performance", "Monetization"]

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(_PROMPTS_DIR), autoescape=False)


class Aspect(BaseModel):
    category: str
    specific_feature: str
    sentiment: str  # Positive | Negative | Mixed | Neutral
    rationale: str


class AbsaResult(BaseModel):
    aspects: list[Aspect]


class DiscoveredPair(BaseModel):
    category: str
    feature: str


class DiscoveryBatchResult(BaseModel):
    pairs: list[DiscoveredPair]
    taxonomy_complete: bool


class CanonicalFeature(BaseModel):
    canonical_name: str
    aliases: list[str]


class CanonicalCategory(BaseModel):
    name: str
    is_seed: bool
    features: list[CanonicalFeature]


class CanonicalTaxonomy(BaseModel):
    categories: list[CanonicalCategory]


def discover_batch(
    review_texts: list[str],
    accumulated: dict[str, list[str]],
    client: genai.Client,
    model: str,
) -> tuple[list[DiscoveredPair], bool]:
    """Return new (category, feature) pairs found in this batch and whether taxonomy is complete."""
    system_prompt = _jinja_env.get_template("discover_batch/system.jinja2").render(
        seed_categories=SEED_CATEGORIES,
        accumulated=accumulated,
    )
    user_prompt = _jinja_env.get_template("discover_batch/user.jinja2").render(reviews=review_texts)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=DiscoveryBatchResult,
        ),
    )
    result = DiscoveryBatchResult.model_validate_json(response.text)
    return result.pairs, result.taxonomy_complete


def canonicalize_taxonomy(
    raw_pairs: dict[str, list[str]],
    client: genai.Client,
    model: str,
) -> list[CanonicalCategory]:
    """Collapse raw discovered pairs into a canonical taxonomy."""
    system_prompt = _jinja_env.get_template("canonicalize/system.jinja2").render(
        seed_categories=SEED_CATEGORIES,
    )
    user_prompt = _jinja_env.get_template("canonicalize/user.jinja2").render(raw_pairs=raw_pairs)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=CanonicalTaxonomy,
        ),
    )
    result = CanonicalTaxonomy.model_validate_json(response.text)
    return result.categories


def analyze_review(
    text: str,
    model: str,
    client: genai.Client,
    taxonomy: dict[str, list[str]] | None = None,
) -> list[Aspect]:
    """Return extracted aspects for a review. Raises on API or parse failure."""
    truncated = text[:2000]
    system_prompt = _jinja_env.get_template("analyze_review/system.jinja2").render(
        seed_categories=SEED_CATEGORIES,
        taxonomy=taxonomy,
    )
    user_prompt = _jinja_env.get_template("analyze_review/user.jinja2").render(review_text=truncated)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=AbsaResult,
        ),
    )
    result = AbsaResult.model_validate_json(response.text)
    return result.aspects
