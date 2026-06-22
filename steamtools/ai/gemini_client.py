"""Thin wrapper around the Gemini API for LLM-based game evaluations."""

import json
from pathlib import Path

from jinja2 import Template
from google import genai
from google.genai import types

from steamtools.config import GEMINI_API_KEY


def evaluate(game_name: str, short_description: str, template_path: Path, model: str) -> dict:
    """Render the prompt template, call Gemini, and return {"score": float, "rationale": str}.

    Raises ValueError if the response is not valid JSON, the score is out of range,
    or the score is not on a 0.5 boundary.
    """
    template = Template(template_path.read_text(encoding="utf-8"))
    prompt = template.render(game_name=game_name, short_description=short_description)

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    raw = response.text
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Non-JSON response from Gemini: {raw!r}") from exc

    score = result.get("score")
    if not isinstance(score, (int, float)):
        raise ValueError(f"Missing or non-numeric score in response: {raw!r}")

    score = float(score)
    if score < 0 or score > 5:
        raise ValueError(f"Score {score} out of range [0, 5]: {raw!r}")
    if round(score * 2) != score * 2:
        raise ValueError(f"Score {score} is not a multiple of 0.5: {raw!r}")

    return {"score": score, "rationale": result.get("rationale", "")}
