import numpy as np
from sentence_transformers import SentenceTransformer


class ReviewEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
        self.model_name = model_name

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, convert_to_numpy=True).astype(np.float32)
