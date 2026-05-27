"""Loader for the global boxcc.md master system prompt.

The master prompt is prepended to BOTH the lead agent and every worker
subagent. It is intentionally kept stable across turns to maximise prompt
cache hits on providers that key on prefix bytes (DeepSeek, OpenAI, Kimi).

The only template placeholder allowed inside `boxcc.md` is
`{knowledge_bases_description}` — see `knowledge.registry` for the source
of truth. All other content stays literal.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from agents.spec_loader import load_prompt_spec

logger = logging.getLogger(__name__)

MASTER_SPEC_PATH = "agentspecs/boxcc.md"
KB_PLACEHOLDER = "{knowledge_bases_description}"
AGENT_CATALOG_BRIEF_PLACEHOLDER = "{agent_catalog_brief}"
DELIVERABLE_TYPES_PLACEHOLDER = "{deliverable_types}"


@lru_cache(maxsize=1)
def _load_raw_master() -> str:
    text = load_prompt_spec(MASTER_SPEC_PATH, "")
    if not text:
        logger.warning("Master spec %s is empty or missing; master prompt will be skipped.", MASTER_SPEC_PATH)
    return text


def _brief_catalog() -> str:
    """Render a compact `id — name — one_liner` list for boxcc.md.

    Shorter than `build_agent_catalog()` (no tags, no critic note) because
    boxcc.md sits at the top of *every* agent's prompt, so we want the
    minimum bytes that still convey "who else exists in this system".
    """
    try:
        from config.app_config import get_app_config

        config = get_app_config()
        workers = config.get_worker_agents()
        critic = config.get_critic_agent()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load registry for catalog brief: %s", exc)
        return "- (registry unavailable)"
    if not workers and not critic:
        return "- (no agents registered)"
    lines = [f"- `{a.id}` {a.name} — {a.one_liner}" for a in workers]
    if critic:
        lines.append(f"- `{critic.id}` {critic.name} — {critic.one_liner}")
    return "\n".join(lines)


def load_master_prompt() -> str:
    """Return the rendered master prompt with all placeholders filled in.

    The raw file is cached process-wide; the dynamic substitutions are
    rebuilt on each call (cheap) so that runtime config changes propagate.

    Placeholders:
      - `{knowledge_bases_description}` — from `knowledge.registry`
      - `{agent_catalog_brief}` — from the agent registry (compact form)
      - `{deliverable_types}` — from `deliverables.registry` (compact form)
    """
    raw = _load_raw_master()
    if not raw:
        return ""

    # Lazy imports to avoid circular dependency: registries → config → agents.
    try:
        from knowledge.registry import describe_knowledge_bases

        kb_description = describe_knowledge_bases()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to render knowledge_bases_description: %s", exc)
        kb_description = "- (none registered)"

    try:
        from deliverables.registry import describe_deliverable_types

        deliverable_types = describe_deliverable_types()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to render deliverable_types: %s", exc)
        deliverable_types = "- (none registered)"

    return (
        raw
        .replace(KB_PLACEHOLDER, kb_description)
        .replace(AGENT_CATALOG_BRIEF_PLACEHOLDER, _brief_catalog())
        .replace(DELIVERABLE_TYPES_PLACEHOLDER, deliverable_types)
    )


def reset_master_prompt_cache() -> None:
    """Drop the cached raw master spec. Used by tests / hot reload."""
    _load_raw_master.cache_clear()
