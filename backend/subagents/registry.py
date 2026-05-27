"""Agent registry — load specialist agent definitions from `config.yaml`.

The registry is a flat list of agents (no more "departments"). Each entry
becomes a `SubagentConfig` runtime instance. `crt` is included like any
other agent but downstream code special-cases it as the critic.
"""

import logging

from config.app_config import get_app_config
from subagents.config import SubagentConfig

logger = logging.getLogger(__name__)


def get_agent_configs() -> list[SubagentConfig]:
    """Load enabled agent configs from `config.agents.registry`."""
    config = get_app_config()
    out: list[SubagentConfig] = []
    for entry in config.agents.registry:
        if not entry.enabled:
            continue
        out.append(SubagentConfig(
            id=entry.id,
            name=entry.name,
            one_liner=entry.one_liner,
            tags=list(entry.tags),
            spec_path=entry.spec_path,
            kb_refs=list(entry.kb_refs),
            max_turns=entry.max_turns,
            enabled=entry.enabled,
            timeout_seconds=config.agents.timeout_seconds,
            # legacy fields fed for any straggling consumer (display_name
            # falls back to name; description falls back to one_liner)
            display_name=entry.name,
            description=entry.one_liner,
        ))
    logger.info("Loaded %d agent(s) from registry", len(out))
    return out


def get_agent_config(agent_id: str) -> SubagentConfig | None:
    """Get a specific agent config by ID."""
    for agent in get_agent_configs():
        if agent.id == agent_id:
            return agent
    return None


# ---- Legacy aliases — keep one release for any straggling caller ----
def get_department_configs() -> list[SubagentConfig]:  # noqa: D401 - shim
    return get_agent_configs()


def get_department_config(dept_id: str) -> SubagentConfig | None:  # noqa: D401
    return get_agent_config(dept_id)
