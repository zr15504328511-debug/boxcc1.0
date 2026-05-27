"""Agents endpoint — return the canonical agent catalog (orc + registry).

Frontend should call this on startup and treat it as the source of truth.
state.json should only persist per-agent toggle overrides, keyed by id.
"""

from fastapi import APIRouter

from agents.prompt import build_lead_system_prompt
from config.app_config import get_app_config
from subagents.config import SubagentConfig
from subagents.prompt import build_department_system_prompt

router = APIRouter()


def _as_subagent(entry) -> SubagentConfig:
    return SubagentConfig(
        id=entry.id,
        name=entry.name,
        one_liner=entry.one_liner,
        tags=list(entry.tags),
        spec_path=entry.spec_path,
        kb_refs=list(entry.kb_refs),
        max_turns=entry.max_turns,
        enabled=entry.enabled,
        display_name=entry.name,
        description=entry.one_liner,
    )


@router.get("/agents")
async def list_agents():
    config = get_app_config()
    agents = [{
        "id": "orc",
        "name": "主席团",
        "one_liner": "理解问题、拆解任务、分派 agent、综合并输出最终答复",
        "tags": ["lead", "orchestrator"],
        "enabled": True,
        "phase": "lead",
        "kb_refs": [],
        "instructions": build_lead_system_prompt(),
    }]
    agents.extend([
        {
            "id": entry.id,
            "name": entry.name,
            "one_liner": entry.one_liner,
            "tags": list(entry.tags),
            "enabled": entry.enabled,
            "phase": "critic" if entry.id == "crt" else "worker",
            "kb_refs": list(entry.kb_refs),
            "instructions": build_department_system_prompt(_as_subagent(entry)),
        }
        for entry in config.agents.registry
    ])
    return agents
