"""Subagent registry - load department definitions from config."""

import logging

from config.app_config import get_app_config
from subagents.config import SubagentConfig

logger = logging.getLogger(__name__)


def get_department_configs() -> list[SubagentConfig]:
    """Load enabled department configs from config.yaml."""
    config = get_app_config()
    departments = []
    for dept in config.departments.agents:
        if not dept.enabled:
            continue
        departments.append(SubagentConfig(
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
        ))
    logger.info("Loaded %d department(s)", len(departments))
    return departments


def get_department_config(dept_id: str) -> SubagentConfig | None:
    """Get a specific department config by ID."""
    for dept in get_department_configs():
        if dept.id == dept_id:
            return dept
    return None