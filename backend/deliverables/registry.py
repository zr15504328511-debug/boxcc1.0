"""Deliverable template loader + lookup.

Mirrors the shape of `knowledge/registry.py` (lru_cache + reset). All
templates come from `AppConfig.deliverable_types`, which is read from
`config.yaml`.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger(__name__)


def _load_types() -> list:
    try:
        from config.app_config import get_app_config

        return list(getattr(get_app_config(), "deliverable_types", []) or [])
    except Exception as exc:  # pragma: no cover
        logger.debug("Could not load deliverable_types from config: %s", exc)
        return []


def list_deliverable_types() -> list:
    """Return all registered deliverable type configs."""
    return _load_types()


def get_deliverable_type(deliverable_id: str):
    """Return the DeliverableTypeConfig for `deliverable_id`, or None."""
    for dt in _load_types():
        if getattr(dt, "id", None) == deliverable_id:
            return dt
    return None


def _tokenize(text: str) -> list[str]:
    """Lowercase + split on punctuation/whitespace for ASCII; pass CJK
    chars through unchanged. Good enough for keyword matching."""
    out: list[str] = []
    buf: list[str] = []
    for ch in text or "":
        if ord(ch) > 0x4e00 - 1 and ord(ch) < 0xa000:
            # CJK: emit each char as its own token so multi-char triggers
            # like '复盘' still match via substring.
            if buf:
                out.append("".join(buf))
                buf = []
            out.append(ch)
        elif ch.isalnum():
            buf.append(ch.lower())
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


@lru_cache(maxsize=1)
def _compiled_triggers() -> list[tuple[str, list[str]]]:
    """Precompute lowercased triggers per deliverable type."""
    out: list[tuple[str, list[str]]] = []
    for dt in _load_types():
        triggers = [str(t).lower().strip() for t in (getattr(dt, "triggers", []) or []) if str(t).strip()]
        out.append((getattr(dt, "id", ""), triggers))
    return out


def match_deliverable_type(user_question: str) -> str | None:
    """Return the deliverable_type id that best matches the user question.

    Strategy: substring-match each trigger against the (lowercased) user
    question; whichever type has the most distinct trigger hits wins.
    Ties broken by registration order. Returns None if nothing matched.
    """
    if not user_question:
        return None
    needle = user_question.lower()
    best_id: str | None = None
    best_hits = 0
    for type_id, triggers in _compiled_triggers():
        hits = sum(1 for t in triggers if t and t in needle)
        if hits > best_hits:
            best_hits = hits
            best_id = type_id
    return best_id


def describe_deliverable_types() -> str:
    """Markdown bullet list for prompt injection into orc.md.

    Each line: `- {id}: {name} | triggers: {triggers} | output: {tool}`
    """
    types = _load_types()
    if not types:
        return "- (none registered)"
    lines: list[str] = []
    for dt in types:
        tid = getattr(dt, "id", "")
        name = getattr(dt, "name", "") or tid
        triggers = ", ".join((getattr(dt, "triggers", []) or [])[:6])
        tool = getattr(dt, "output_tool", "") or "(none)"
        lines.append(f"- `{tid}` ({name}) — triggers: {triggers or '(none)'} — output_tool: `{tool}`")
    return "\n".join(lines)


def render_deliverable_brief(deliverable_id: str) -> str:
    """Render a full template as markdown for orc / critic injection.

    Includes structure, worker contribution map, quality gates. Used both
    in the orc prompt (so orc knows the recipe) and in the critic task
    packet (so critic reviews against the right checklist).
    """
    dt = get_deliverable_type(deliverable_id)
    if dt is None:
        return f"(deliverable type '{deliverable_id}' not registered)"

    lines: list[str] = []
    lines.append(f"## Deliverable template: {getattr(dt, 'name', '') or deliverable_id} ({deliverable_id})")
    desc = getattr(dt, "description", "")
    if desc:
        lines.append(f"\n{desc}")
    voice = getattr(dt, "voice", "")
    if voice:
        lines.append(f"\n**Voice / tone:** {voice}")
    tool = getattr(dt, "output_tool", "")
    theme = getattr(dt, "default_theme", "")
    if tool:
        lines.append(f"\n**Output tool:** `{tool}`" + (f" (default_theme=`{theme}`)" if theme else ""))

    suggested = getattr(dt, "suggested_workers", []) or []
    required = getattr(dt, "required_workers", []) or []
    if suggested or required:
        lines.append("\n**Workers:**")
        if required:
            lines.append(f"- required: {', '.join(required)}")
        if suggested:
            lines.append(f"- suggested: {', '.join(suggested)}")

    structure = getattr(dt, "structure", []) or []
    if structure:
        lines.append("\n**Structure (in order):**")
        for s in structure:
            stype = getattr(s, "type", "")
            req = "**required**" if getattr(s, "required", False) else "optional"
            mn = getattr(s, "min_count", 0)
            mx = getattr(s, "max_count", 99)
            rng = ""
            if mx < 99 or mn > 0:
                rng = f" [{mn}–{mx}]"
            notes = (getattr(s, "notes", "") or "").strip()
            head = f"- `{stype}` ({req}){rng}"
            lines.append(head)
            if notes:
                indented = "\n".join("    " + line for line in notes.splitlines() if line.strip())
                lines.append(indented)

    wcm = getattr(dt, "worker_contribution_map", {}) or {}
    if wcm:
        lines.append("\n**Worker contribution map:**")
        for worker_id, sections in wcm.items():
            secs = ", ".join(sections) if isinstance(sections, list) else str(sections)
            lines.append(f"- `{worker_id}` → {secs}")

    gates = getattr(dt, "quality_gates", []) or []
    if gates:
        lines.append("\n**Quality gates (critic checklist):**")
        for g in gates:
            lines.append(f"- {g}")

    return "\n".join(lines)


def reset_deliverables_cache() -> None:
    """Drop the compiled-triggers cache. Use after config reload."""
    _compiled_triggers.cache_clear()
