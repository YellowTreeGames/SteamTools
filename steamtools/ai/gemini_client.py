"""Thin wrapper around the Gemini API for LLM-based game evaluations."""

import json
from pathlib import Path

from google import genai
from google.genai import types
from jinja2 import Template

from steamtools.config import GEMINI_API_KEY

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _render_prompt(template_path: Path, game_name: str, short_description: str) -> str:
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.render(game_name=game_name, short_description=short_description)


def _parse_eval_response(raw: str) -> dict:
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Non-JSON response from Gemini: {raw!r}") from exc

    if not isinstance(result, dict):
        raise ValueError(f"Missing or non-numeric score in response: {raw!r}")

    score = result.get("score")
    if not isinstance(score, (int, float)):
        raise ValueError(f"Missing or non-numeric score in response: {raw!r}")

    score = float(score)
    if score < 0 or score > 5:
        raise ValueError(f"Score {score} out of range [0, 5]: {raw!r}")
    if round(score * 2) != score * 2:
        raise ValueError(f"Score {score} is not a multiple of 0.5: {raw!r}")

    return {"score": score, "rationale": result.get("rationale", "")}


def evaluate(game_name: str, short_description: str, template_path: Path, model: str) -> dict:
    """Render the prompt template, call Gemini, and return {"score": float, "rationale": str}.

    Raises ValueError if the response is not valid JSON, the score is out of range,
    or the score is not on a 0.5 boundary.
    """
    prompt = _render_prompt(template_path, game_name, short_description)
    response = _get_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return _parse_eval_response(response.text or "")
