"""Generic ChromaDB wrapper. Collection names are chosen by the caller."""

from pathlib import Path

import chromadb
import numpy as np

CHROMA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "vectordb"


class VectorManager:
    def __init__(self, path: Path = CHROMA_PATH):
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(name)

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        col = self.get_or_create_collection(collection_name)
        col.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def get_all_embeddings(self, collection_name: str) -> tuple[list[str], np.ndarray]:
        col = self.get_or_create_collection(collection_name)
        result = col.get(include=["embeddings"])
        ids = result["ids"]
        embeddings = np.array(result["embeddings"], dtype=np.float32)
        return ids, embeddings

    def query_by_vector(
        self, collection_name: str, vector: list[float], n_results: int = 10
    ) -> list[dict]:
        col = self.get_or_create_collection(collection_name)
        result = col.query(
            query_embeddings=[vector],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for i, doc_id in enumerate(result["ids"][0]):
            out.append({
                "id": doc_id,
                "document": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            })
        return out

    def count(self, collection_name: str) -> int:
        return self.get_or_create_collection(collection_name).count()

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]
