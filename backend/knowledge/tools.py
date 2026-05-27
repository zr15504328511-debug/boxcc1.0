"""Knowledge-base tool exposed to worker agents.

Workers don't read KBs directly. orc decides which KBs each worker may
consult by setting `task_packet.kb_refs`. The executor publishes that
allowlist into a contextvar **before** invoking the worker's LangGraph
agent; the `query_knowledge_base` tool below enforces the allowlist on
every call. If a worker tries to consult a KB it wasn't authorised for,
the tool returns a clear "not authorised" message instead of querying.

This keeps three layers of access control honest:
  1. config.yaml `knowledge_bases:` — the registry of KBs the system knows about
  2. agentspecs/<id>.md `kb_refs:` — the KBs the agent type may EVER use
  3. task_packet.kb_refs — the KBs orc actually grants for THIS task

The tool intersects #2 and #3 — orc cannot grant a KB the agent isn't
declared to handle, and the agent cannot reach a KB orc didn't grant.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Annotated

from langchain_core.tools import tool

from knowledge.registry import get_retriever

logger = logging.getLogger(__name__)

# Per-invocation allowlist. Set by the executor right before calling
# `agent.ainvoke`, reset in `finally`. Default empty → no KB access.
_kb_allowlist_var: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "kb_allowlist", default=frozenset()
)


def set_kb_allowlist(kb_ids: list[str] | set[str] | None) -> contextvars.Token:
    """Publish the authorised KB id set for this invocation.

    Returns a token the executor must pass to `reset_kb_allowlist` once
    the worker has finished.
    """
    return _kb_allowlist_var.set(frozenset(kb_ids or []))


def reset_kb_allowlist(token: contextvars.Token) -> None:
    _kb_allowlist_var.reset(token)


def get_kb_allowlist() -> frozenset[str]:
    return _kb_allowlist_var.get()


def _format_chunks(chunks, kb_id: str) -> str:
    if not chunks:
        return f"[KB:{kb_id}] (no results)"
    parts = [f"[KB:{kb_id}] retrieved {len(chunks)} chunk(s):"]
    for i, c in enumerate(chunks, start=1):
        source = getattr(c, "source", "?")
        content = getattr(c, "content", "")
        score = getattr(c, "score", 0.0)
        parts.append(f"  ({i}) source={source} score={score:.2f}\n      {content}")
    return "\n".join(parts)


@tool
def query_knowledge_base(
    kb_id: Annotated[str, "The id of the knowledge base to query (must be in your authorised kb_refs for this task)."],
    query: Annotated[str, "The natural-language question or keyword string. Be specific — 'lyocell shrinkage 30 wash' is better than 'fabric stuff'."],
    k: Annotated[int, "Max number of chunks to return. Default 5; raise to 10 only when you really need breadth."] = 5,
) -> str:
    """Retrieve relevant chunks from a registered knowledge base.

    The list of KBs you may consult is restricted by orc's grant in this
    task's `kb_refs`. If you call this tool with a `kb_id` you weren't
    granted, the tool returns an authorisation error — do NOT retry with
    the same id; instead say in your answer that the data is unavailable
    and proceed with your best knowledge.

    Returns plain text formatted as `[KB:<id>] retrieved N chunk(s): ...`.
    On failure or no-match, returns `(no results)` or an error string.
    """
    allowlist = get_kb_allowlist()
    if kb_id not in allowlist:
        if not allowlist:
            return (
                f"[KB:{kb_id}] not authorised — orc did not grant any KB for this task. "
                "Answer from your own knowledge and flag the data gap to the user."
            )
        return (
            f"[KB:{kb_id}] not authorised — you may only query: {sorted(allowlist)}. "
            "Do not retry with this id."
        )

    retriever = get_retriever(kb_id)
    if retriever is None:
        return f"[KB:{kb_id}] not found in registry. Check config.yaml `knowledge_bases:` section."

    try:
        chunks = retriever.retrieve(query, k=max(1, min(int(k or 5), 20)))
    except Exception as exc:
        logger.warning("KB retrieve failed for %s: %s", kb_id, exc)
        return f"[KB:{kb_id}] retrieve error: {exc}"

    return _format_chunks(chunks, kb_id)
