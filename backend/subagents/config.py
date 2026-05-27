"""Subagent configuration dataclass.

Runtime dataclass passed around the executor / prompt layer. The Pydantic
counterpart in `config.app_config.AgentConfig` is what the YAML actually
deserialises into; this dataclass adds runtime-only fields (e.g.
`timeout_seconds`) without polluting the config schema.
"""

from dataclasses import dataclass, field


@dataclass
class SubagentConfig:
    """Configuration for one registered agent."""

    id: str
    name: str
    one_liner: str = ""
    tags: list[str] = field(default_factory=list)
    spec_path: str = ""
    kb_refs: list[str] = field(default_factory=list)
    max_turns: int = 25
    enabled: bool = True
    # runtime-only — not in the YAML schema
    timeout_seconds: int = 300
    # legacy aliases (read-only) for any straggling consumer; safe to remove
    # once tools.py / executor.py stop referencing them.
    display_name: str = ""
    description: str = ""
