"""Subagent registry - load department definitions from config and user overlay."""

import json
import logging

from config.app_config import get_app_config
from config.paths import get_data_dir
from subagents.config import SubagentConfig

logger = logging.getLogger(__name__)


def _as_subagent_config(raw, *, timeout_seconds: int) -> SubagentConfig | None:
    if not isinstance(raw, dict):
        return None
    dept_id = str(raw.get('id') or '').strip()
    if not dept_id:
        return None
    phase = str(raw.get('phase') or '').strip()
    if phase == 'lead' or dept_id == 'orc':
        return None
    return SubagentConfig(
        id=dept_id,
        name=str(raw.get('name') or raw.get('display_name') or dept_id),
        display_name=str(raw.get('display_name') or raw.get('name') or dept_id),
        description=str(raw.get('description') or raw.get('desc') or ''),
        enabled=raw.get('enabled') is not False,
        model=str(raw.get('model') or 'inherit'),
        system_prompt=str(raw.get('system_prompt') or raw.get('instructions') or ''),
        spec_path=str(raw.get('spec_path') or ''),
        skill_packs=list(raw.get('skill_packs') or []),
        max_turns=int(raw.get('max_turns') or 25),
        timeout_seconds=timeout_seconds,
    )


def _load_user_agent_overlay(timeout_seconds: int) -> list[SubagentConfig]:
    path = get_data_dir() / 'agents.json'
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('Failed to load user agent overlay %s: %s', path, exc)
        return []
    items = raw if isinstance(raw, list) else raw.get('agents') if isinstance(raw, dict) else []
    result: list[SubagentConfig] = []
    for item in items or []:
        config = _as_subagent_config(item, timeout_seconds=timeout_seconds)
        if config is not None:
            result.append(config)
    return result


def get_department_configs() -> list[SubagentConfig]:
    """Load enabled department configs from config.yaml plus user-defined overlay."""
    config = get_app_config()
    departments: dict[str, SubagentConfig] = {}
    for dept in config.departments.agents:
        if not dept.enabled:
            continue
        departments[dept.id] = SubagentConfig(
            id=dept.id,
            name=dept.name,
            display_name=dept.display_name,
            description=dept.description,
            enabled=dept.enabled,
            model=dept.model,
            system_prompt=dept.system_prompt,
            spec_path=dept.spec_path,
            skill_packs=list(dept.skill_packs),
            max_turns=dept.max_turns if hasattr(dept, 'max_turns') else 25,
            timeout_seconds=config.departments.timeout_seconds,
        )

    for user_dept in _load_user_agent_overlay(config.departments.timeout_seconds):
        if user_dept.enabled:
            departments[user_dept.id] = user_dept
        else:
            departments.pop(user_dept.id, None)

    result = list(departments.values())
    logger.info("Loaded %d department(s)", len(result))
    return result


def get_department_config(dept_id: str) -> SubagentConfig | None:
    """Get a specific department config by ID."""
    for dept in get_department_configs():
        if dept.id == dept_id:
            return dept
    return None
