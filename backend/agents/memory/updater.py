"""Memory updater - reads, updates, and writes memory using LLM extraction."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.memory.prompt import MEMORY_UPDATE_PROMPT, format_conversation_for_update
from config.app_config import get_app_config
from config.paths import resolve_path
from models.factory import create_chat_model

logger = logging.getLogger(__name__)


def _create_empty_memory() -> dict[str, Any]:
    return {
        "version": "1.0",
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


def _get_memory_path() -> Path:
    config = get_app_config()
    return resolve_path(config.memory.storage_path)


# Cache: (memory_data, file_mtime)
_cache: tuple[dict[str, Any], float | None] | None = None


def get_memory_data() -> dict[str, Any]:
    global _cache
    path = _get_memory_path()

    try:
        mtime = path.stat().st_mtime if path.exists() else None
    except OSError:
        mtime = None

    if _cache is None or _cache[1] != mtime:
        _cache = (_load_memory(path), mtime)

    return _cache[0]


def _load_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _create_empty_memory()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load memory: %s", e)
        return _create_empty_memory()


def _save_memory(data: dict[str, Any]) -> bool:
    global _cache
    path = _get_memory_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"

        temp = path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp.replace(path)

        _cache = (data, path.stat().st_mtime)
        logger.info("Memory saved to %s", path)
        return True
    except OSError as e:
        logger.error("Failed to save memory: %s", e)
        return False


def update_memory_from_conversation(
    messages: list[Any],
    thread_id: str | None = None,
    agent_name: str | None = None,
) -> bool:
    """Update memory based on conversation messages using LLM extraction."""
    config = get_app_config()
    if not config.memory.enabled or not messages:
        return False

    try:
        current = get_memory_data()
        conversation = format_conversation_for_update(messages)
        if not conversation.strip():
            return False

        prompt = MEMORY_UPDATE_PROMPT.format(
            current_memory=json.dumps(current, indent=2, ensure_ascii=False),
            conversation=conversation,
        )

        model = create_chat_model()
        response = model.invoke(prompt)
        text = response.content
        if isinstance(text, list):
            text = "\n".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in text
            )

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        updates = json.loads(text)
        updated = _apply_updates(current, updates, thread_id)
        return _save_memory(updated)

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse memory update response: %s", e)
        return False
    except Exception:
        logger.exception("Memory update failed")
        return False


def _apply_updates(
    current: dict[str, Any],
    updates: dict[str, Any],
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Apply LLM-generated updates to memory."""
    config = get_app_config()
    now = datetime.utcnow().isoformat() + "Z"

    # Update user sections
    for section in ["workContext", "personalContext", "topOfMind"]:
        data = updates.get("user", {}).get(section, {})
        if data.get("shouldUpdate") and data.get("summary"):
            current["user"][section] = {"summary": data["summary"], "updatedAt": now}

    # Update history sections
    for section in ["recentMonths", "earlierContext", "longTermBackground"]:
        data = updates.get("history", {}).get(section, {})
        if data.get("shouldUpdate") and data.get("summary"):
            current["history"][section] = {"summary": data["summary"], "updatedAt": now}

    # Remove facts
    to_remove = set(updates.get("factsToRemove", []))
    if to_remove:
        current["facts"] = [f for f in current.get("facts", []) if f.get("id") not in to_remove]

    # Add new facts (deduplicate)
    existing_keys = {f.get("content", "").strip() for f in current.get("facts", [])}
    for fact in updates.get("newFacts", []):
        confidence = fact.get("confidence", 0.5)
        if confidence < 0.7:
            continue
        content = fact.get("content", "").strip()
        if not content or content in existing_keys:
            continue

        current["facts"].append({
            "id": f"fact_{uuid.uuid4().hex[:8]}",
            "content": content,
            "category": fact.get("category", "context"),
            "confidence": confidence,
            "createdAt": now,
            "source": thread_id or "unknown",
        })
        existing_keys.add(content)

    # Enforce max facts
    if len(current["facts"]) > config.memory.max_facts:
        current["facts"] = sorted(
            current["facts"],
            key=lambda f: f.get("confidence", 0),
            reverse=True,
        )[:config.memory.max_facts]

    return current
