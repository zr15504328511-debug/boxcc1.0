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
    """Format memory data for injection into the system prompt."""
    if not memory_data:
        return ""

    parts = []

    # User context
    user = memory_data.get("user", {})
    for key in ["workContext", "personalContext", "topOfMind"]:
        section = user.get(key, {})
        summary = section.get("summary", "")
        if summary:
            label = {"workContext": "工作背景", "personalContext": "个人偏好", "topOfMind": "当前关注"}[key]
            parts.append(f"[{label}] {summary}")

    # History
    history = memory_data.get("history", {})
    for key in ["recentMonths", "earlierContext"]:
        section = history.get(key, {})
        summary = section.get("summary", "")
        if summary:
            label = {"recentMonths": "近期历史", "earlierContext": "早期背景"}[key]
            parts.append(f"[{label}] {summary}")

    # Facts (sorted by confidence, limited by token budget)
    facts = memory_data.get("facts", [])
    if facts:
        sorted_facts = sorted(facts, key=lambda f: f.get("confidence", 0), reverse=True)
        fact_lines = []
        for f in sorted_facts[:20]:  # Max 20 facts
            fact_lines.append(f"- {f.get('content', '')}")
        if fact_lines:
            parts.append("[关键事实]\n" + "\n".join(fact_lines))

    result = "\n\n".join(parts)

    # Rough token limit (4 chars ≈ 1 token for Chinese)
    char_limit = max_tokens * 4
    if len(result) > char_limit:
        result = result[:char_limit] + "..."

    return result
