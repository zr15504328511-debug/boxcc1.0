"""ChromaDB-backed retriever implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.paths import get_data_dir, resolve_path
from knowledge.retriever import RetrievalChunk


class ChromaRetriever:
    """Retrieve KB chunks from a local persistent ChromaDB collection."""

    def __init__(self, kb_id: str, description: str = "", config: dict | None = None):
        cfg = config or {}
        self.kb_id = kb_id
        self.description = description
        self.config = cfg
        self.collection = None
        self._init_error: str | None = None

        try:
            import chromadb
            from chromadb.utils import embedding_functions

            path = self._resolve_path(cfg.get("path"))
            self.client = chromadb.PersistentClient(path=str(path))
            embedding_model = cfg.get("embedding_model")
            embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedding_model)
                if embedding_model
                else embedding_functions.DefaultEmbeddingFunction()
            )
            self.collection = self.client.get_or_create_collection(
                name=kb_id,
                embedding_function=embedding_function,
            )
        except Exception as exc:  # pragma: no cover - exercised by smoke path when env is broken
            self._init_error = str(exc)

    def _resolve_path(self, configured_path: Any) -> Path:
        if configured_path:
            return resolve_path(str(configured_path))
        return get_data_dir() / "kb" / self.kb_id

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]:
        if self._init_error:
            return [self._error_chunk(self._init_error)]
        if self.collection is None:
            return [self._error_chunk("collection is not initialized")]

        try:
            results = self.collection.query(query_texts=[query], n_results=max(1, int(k or 5)))
            documents = (results.get("documents") or [[]])[0] or []
            metadatas = (results.get("metadatas") or [[]])[0] or []
            distances = (results.get("distances") or [[]])[0] or []

            chunks: list[RetrievalChunk] = []
            for i, doc in enumerate(documents):
                meta = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
                distance = distances[i] if i < len(distances) and distances[i] is not None else 1.0
                score = max(0.0, 1.0 - float(distance))
                chunks.append(
                    RetrievalChunk(
                        source=str(meta.get("source") or f"chroma://{self.kb_id}/{i}"),
                        content=str(doc or ""),
                        score=score,
                    )
                )
            return chunks
        except Exception as exc:
            return [self._error_chunk(str(exc))]

    def _error_chunk(self, message: str) -> RetrievalChunk:
        return RetrievalChunk(
            source=f"chroma://{self.kb_id}/error",
            content=f"(chroma retrieve error: {message})",
            score=0.0,
        )
