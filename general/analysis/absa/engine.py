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


def analyze_review(text: str, model: str, client: genai.Client) -> list[Aspect] | None:
    """Return extracted aspects for a review, or None on API/parse failure."""
    truncated = text[:2000]

    system_prompt = _jinja_env.get_template("analyze_review/system.jinja2").render(seed_categories=SEED_CATEGORIES)
    user_prompt = _jinja_env.get_template("analyze_review/user.jinja2").render(review_text=truncated)

    try:
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
    except Exception:
        return None
