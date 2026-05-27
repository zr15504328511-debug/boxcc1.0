"""Smoke test for Chroma-backed KB retrieval and worker tool access."""

from __future__ import annotations

from config.app_config import reload_app_config
from knowledge.registry import get_retriever, reset_registry_cache
from knowledge.tools import query_knowledge_base, reset_kb_allowlist, set_kb_allowlist


def main() -> None:
    reload_app_config()
    reset_registry_cache()

    r = get_retriever("compliance_contract_kb")
    chunks = r.retrieve("广告法禁用词", k=3) if r else []
    for c in chunks:
        print(c.score, c.source, c.content[:100])

    tok = set_kb_allowlist(["compliance_contract_kb"])
    try:
        print(query_knowledge_base.invoke({"kb_id": "compliance_contract_kb", "query": "禁用词"}))
    finally:
        reset_kb_allowlist(tok)


if __name__ == "__main__":
    main()
