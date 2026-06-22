import json

from google import genai
from google.genai import types

from steamtools.config import GEMINI_API_KEY, GEMINI_MODEL

_PROMPT_TEMPLATE = """\
You are analyzing a cluster of Steam game reviews. Based on the sample reviews below, \
identify the main topic or theme discussed.

Reviews:
{reviews}

Respond with JSON only, in this exact format:
{{"category_name": "short topic label (3-6 words)", "description": "one sentence describing what this cluster is about"}}"""


class ClusterLabeler:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or GEMINI_MODEL
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    def label_cluster(self, sample_reviews: list[str]) -> dict:
        """Prompt Gemini with up to 10 sample reviews and return {category_name, description}."""
        reviews_text = "\n\n".join(f"- {r}" for r in sample_reviews[:10])
        prompt = _PROMPT_TEMPLATE.format(reviews=reviews_text)

        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        try:
            result = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            return {"category_name": "Unknown", "description": ""}

        return {
            "category_name": result.get("category_name", "Unknown"),
            "description": result.get("description", ""),
        }
