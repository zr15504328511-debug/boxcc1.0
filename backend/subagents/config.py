"""Subagent configuration dataclass."""

from dataclasses import dataclass, field


@dataclass
class SubagentConfig:
    """Configuration for a department subagent."""

    id: str
    name: str
    display_name: str = ""
    description: str = ""
    enabled: bool = True
    model: str = "inherit"
    system_prompt: str = ""
    spec_path: str = ""
    skill_packs: list[str] = field(default_factory=list)
    max_turns: int = 25
    timeout_seconds: int = 300