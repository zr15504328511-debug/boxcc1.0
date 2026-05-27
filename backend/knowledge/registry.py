"""Knowledge base registry.

Reads `knowledge_bases:` from `config.yaml` and exposes:

* `describe_knowledge_bases()` — markdown bullet list for injection into
  the `boxcc.md` master prompt via the `{knowledge_bases_description}`
  placeholder.
* `get_knowledge_base(kb_id)` / `get_retriever(kb_id)` — lookups for
  future worker-side tool integration.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from knowledge.retriever import BaseRetriever, build_retriever

logger = logging.getLogger(__name__)


def _load_kbs() -> list:
    try:
        from config.app_config import get_app_config

        return list(getattr(get_app_config(), "knowledge_bases", []) or [])
    except Exception as exc:  # pragma: no cover
        logger.debug("Could not load knowledge_bases from config: %s", exc)
        return []


def describe_knowledge_bases() -> str:
    """Render the markdown KB list for prompt injection.

    Returns "- (none registered)" when no KB is configured.
    """
    kbs = _load_kbs()
    if not kbs:
        return "- (none registered)"
    lines = []
    for kb in kbs:
        kb_id = getattr(kb, "id", None)
        name = getattr(kb, "name", None) or kb_id or "(unnamed)"
        desc = getattr(kb, "description", None) or "no description"
        if not kb_id:
            continue
        lines.append(f"- {kb_id}: {name} | {desc}")
    return "\n".join(lines) if lines else "- (none registered)"


def get_knowledge_base(kb_id: str):
    """Return the KnowledgeBaseConfig for `kb_id`, or None."""
    for kb in _load_kbs():
        if getattr(kb, "id", None) == kb_id:
            return kb
    return None


@lru_cache(maxsize=32)
def get_retriever(kb_id: str) -> BaseRetriever | None:
    """Return (and cache) a retriever instance for `kb_id`, or None."""
    kb = get_knowledge_base(kb_id)
    if kb is None:
        return None
    return build_retriever(
        getattr(kb, "retriever", "noop"),
        kb_id=kb_id,
        description=getattr(kb, "description", "") or "",
        config=dict(getattr(kb, "config", {}) or {}),
    )


def reset_registry_cache() -> None:
    """Drop cached retriever instances. Use after config reload."""
    get_retriever.cache_clear()
