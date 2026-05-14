"""Agents endpoint - list effective agent definitions."""

from fastapi import APIRouter

from agents.prompt import build_lead_system_prompt
from subagents.config import SubagentConfig
from subagents.prompt import build_department_system_prompt
from subagents.registry import get_department_configs

router = APIRouter()


def _as_subagent(agent) -> SubagentConfig:
    return SubagentConfig(
        id=agent.id,
        name=agent.name,
        display_name=agent.display_name,
        description=agent.description,
        enabled=agent.enabled,
        model=agent.model,
        system_prompt=agent.system_prompt,
        spec_path=agent.spec_path,
        skill_packs=list(agent.skill_packs),
        max_turns=agent.max_turns,
    )


@router.get("/agents")
async def list_agents():
    agents = [{
        "id": "orc",
        "name": "主席团",
        "display_name": "主席团",
        "description": "负责理解问题、分发任务、整合结果并输出最终答复",
        "enabled": True,
        "phase": "lead",
        "skill_packs": [],
        "instructions": build_lead_system_prompt(),
    }]
    agents.extend([
        {
            "id": agent.id,
            "name": agent.name,
            "display_name": agent.display_name or agent.name or agent.id,
            "description": agent.description,
            "enabled": agent.enabled,
            "phase": "critic" if agent.id == "crt" else "worker",
            "skill_packs": list(agent.skill_packs),
            "instructions": build_department_system_prompt(_as_subagent(agent)),
        }
        for agent in get_department_configs()
    ])
    return agents
