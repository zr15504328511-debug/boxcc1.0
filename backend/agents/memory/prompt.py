"""Memory update and injection prompt templates for boxcc."""

import json
from typing import Any

MEMORY_UPDATE_PROMPT = """You are a memory manager for a fashion planning AI assistant (boxcc).
Analyze the conversation below and update the memory accordingly.

Current memory:
{current_memory}

Recent conversation:
{conversation}

Return a JSON object with updates. Only include sections that need updating.
Format:
{{
  "user": {{
    "workContext": {{"shouldUpdate": true/false, "summary": "..."}},
    "personalContext": {{"shouldUpdate": true/false, "summary": "..."}},
    "topOfMind": {{"shouldUpdate": true/false, "summary": "..."}}
  }},
  "history": {{
    "recentMonths": {{"shouldUpdate": true/false, "summary": "..."}},
    "earlierContext": {{"shouldUpdate": true/false, "summary": "..."}},
    "longTermBackground": {{"shouldUpdate": true/false, "summary": "..."}}
  }},
  "newFacts": [
    {{"content": "...", "category": "fabric|pricing|planning|preference|knowledge|context", "confidence": 0.0-1.0}}
  ],
  "factsToRemove": ["fact_id_1", "fact_id_2"]
}}

Guidelines:
- Focus on fashion/clothing domain knowledge: fabrics, pricing, brands, planning patterns
- Extract user preferences, brand information, price points, supplier details
- workContext = current project/task info
- personalContext = user preferences and working style
- topOfMind = most recent important context
- Only set shouldUpdate=true if the section genuinely needs to change
- Facts should be specific, verifiable pieces of information
- Confidence: 0.9+ for explicitly stated facts, 0.7-0.9 for strongly implied, below 0.7 skip

Return ONLY valid JSON, no markdown formatting."""


def format_conversation_for_update(messages: list[Any]) -> str:
    """Format conversation messages for the memory update prompt."""
    parts = []
    for msg in messages:
        msg_type = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        if isinstance(content, str) and content.strip():
            role = "User" if msg_type == "human" else "Assistant"
            parts.append(f"{role}: {content[:2000]}")
    return "\n\n".join(parts)


def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
    """Legacy single-block formatter. Prefer `format_memory_split` for
    prompt-cache-friendly injection. Kept for backwards compatibility."""
    core = format_memory_core(memory_data)
    facts = format_memory_facts(memory_data, max_tokens=max_tokens)
    parts = [p for p in (core, facts) if p]
    result = "\n\n".join(parts)
    char_limit = max_tokens * 4
    if len(result) > char_limit:
        result = result[: char_limit] + "..."
    return result


def format_memory_core(memory_data: dict[str, Any]) -> str:
    """Stable "core profile" memory: user + history summaries.

    These sections are written by the memory updater as full-string
    summaries that turn over slowly, so injecting them as their own
    block maximises prompt-cache hits across turns.
    """
    if not memory_data:
        return ""
    parts: list[str] = []

    user = memory_data.get("user", {})
    for key in ["workContext", "personalContext", "topOfMind"]:
        section = user.get(key, {})
        summary = section.get("summary", "")
        if summary:
            label = {"workContext": "工作背景", "personalContext": "个人偏好", "topOfMind": "当前关注"}[key]
            parts.append(f"[{label}] {summary}")

    history = memory_data.get("history", {})
    for key in ["recentMonths", "earlierContext"]:
        section = history.get(key, {})
        summary = section.get("summary", "")
        if summary:
            label = {"recentMonths": "近期历史", "earlierContext": "早期背景"}[key]
            parts.append(f"[{label}] {summary}")

    return "\n\n".join(parts)


def format_memory_facts(memory_data: dict[str, Any], *, max_tokens: int = 2000, max_facts: int = 40) -> str:
    """Append-only facts block, ordered by `createdAt` ascending.

    Sorting by creation time (oldest first) means new facts always land at
    the end of the rendered block, so existing prefix bytes never shift.
    This is the property that keeps providers' prompt cache happy.

    If we exceed the max-facts cap we drop from the front (oldest), which
    will break the cache once but keeps the tail stable thereafter.
    """
    facts = list(memory_data.get("facts", []))
    if not facts:
        return ""

    def _ts(fact: dict[str, Any]) -> str:
        # Fall back to id so ordering is at least deterministic.
        return str(fact.get("createdAt") or fact.get("id") or "")

    facts.sort(key=_ts)
    if len(facts) > max_facts:
        facts = facts[-max_facts:]

    lines = [f"- {f.get('content', '').strip()}" for f in facts if f.get("content")]
    if not lines:
        return ""

    rendered = "[关键事实]\n" + "\n".join(lines)
    char_limit = max_tokens * 4
    if len(rendered) > char_limit:
        # Trim from the front (oldest) to keep the tail stable.
        excess = len(rendered) - char_limit
        rendered = rendered[excess:]
    return rendered
