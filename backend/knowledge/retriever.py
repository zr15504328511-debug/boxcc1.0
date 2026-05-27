"""Knowledge base retriever interface.

Workers do not retrieve directly today. This module defines the contract
for future tool integration (e.g. `query_knowledge_base(kb_id, query)`)
and provides a Noop default so the registry has something to return.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Protocol


@dataclass
class RetrievalChunk:
    """A single retrieved snippet returned to a worker."""

    source: str
    content: str
    score: float = 0.0


class BaseRetriever(Protocol):
    """Minimal retriever contract.

    Real implementations (Chroma, Elasticsearch, in-house RAG) should
    implement `retrieve` and live in their own module under `knowledge/`.
    """

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]: ...


class NoopRetriever:
    """Default retriever that returns a single explanatory chunk.

    Allows the pipeline to flow even when no real KB backend is wired,
    while making it obvious to the worker that nothing was retrieved.
    """

    def __init__(self, kb_id: str, description: str = "") -> None:
        self.kb_id = kb_id
        self.description = description

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]:  # noqa: ARG002
        return [
            RetrievalChunk(
                source=f"kb://{self.kb_id}",
                content=(
                    f"(Knowledge base '{self.kb_id}' has no retriever configured; "
                    f"answer from prior knowledge. KB description: {self.description or 'n/a'})"
                ),
                score=0.0,
            )
        ]


_RETRIEVER_TYPES: dict[str, type | str] = {
    "noop": NoopRetriever,
    "chroma": "knowledge.chroma_retriever:ChromaRetriever",
}


def _resolve_retriever_type(retriever_type: str) -> type:
    cls_or_path = _RETRIEVER_TYPES.get(retriever_type, NoopRetriever)
    if isinstance(cls_or_path, str):
        module_name, class_name = cls_or_path.split(":", 1)
        cls = getattr(import_module(module_name), class_name)
        _RETRIEVER_TYPES[retriever_type] = cls
        return cls
    return cls_or_path


def build_retriever(retriever_type: str, *, kb_id: str, description: str = "", config: dict | None = None) -> BaseRetriever:
    """Instantiate a retriever by type id.

    Unknown types fall back to NoopRetriever so misconfiguration never
    crashes the run.
    """
    cls = _resolve_retriever_type(retriever_type)
    if cls is NoopRetriever:
        return NoopRetriever(kb_id=kb_id, description=description)
    return cls(kb_id=kb_id, description=description, config=config or {})  # type: ignore[call-arg]
