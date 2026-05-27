"""Application configuration - YAML loader with env var resolution and caching."""

import logging
import os
from pathlib import Path
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    name: str
    display_name: str = ""
    use: str
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7

    class Config:
        extra = "allow"


class AgentConfig(BaseModel):
    """One entry in the agent registry.

    The flat registry replaces the legacy `DepartmentsConfig` model. Each
    agent is its own specialist (e.g. `mer_plan`, `biz_legal`), not a
    "center" that groups multiple roles. `crt` (critic) is part of the
    same list but special-cased downstream as the validation authority.
    """

    id: str
    name: str
    one_liner: str = ""
    tags: list[str] = Field(default_factory=list)
    spec_path: str = ""
    kb_refs: list[str] = Field(default_factory=list)
    max_turns: int = 25
    enabled: bool = True

    class Config:
        extra = "allow"


class AgentsConfig(BaseModel):
    """Top-level registry container. Mirrors what used to be `departments`."""

    max_concurrent: int = 6
    timeout_seconds: int = 1800
    registry: list[AgentConfig] = Field(default_factory=list)


class LeadAgentConfig(BaseModel):
    system_prompt: str = ""
    spec_path: str = ""


class SummarizationConfig(BaseModel):
    enabled: bool = True
    max_token_threshold: int = 12000
    keep_recent_messages: int = 8


class MemoryConfig(BaseModel):
    enabled: bool = True
    storage_path: str = "data/memory.json"
    debounce_seconds: int = 30
    max_facts: int = 100
    max_injection_tokens: int = 2000


class TitleConfig(BaseModel):
    enabled: bool = True
    max_chars: int = 60


class CheckpointerConfig(BaseModel):
    type: str = "sqlite"
    connection_string: str = "data/checkpoints.db"


class DeliverableSection(BaseModel):
    """One section/slide slot in a deliverable template.

    `type` is interpreted by the output tool (e.g. for management_ppt
    `cover` / `agenda` / `divider` / `content` / `data` / `closing`;
    for product_detail_page `hero` / `highlights` / `fabric` / `size_table`
    / `scenes` / `care` / `faq`).
    """

    type: str
    required: bool = False
    min_count: int = 0
    max_count: int = 99
    repeats: str = ""  # semantic placeholder (e.g. "chapters", "products")
    notes: str = ""    # plain-language hint orc reads when filling this slot

    class Config:
        extra = "allow"


class DeliverableTypeConfig(BaseModel):
    """A reusable recipe for one kind of deliverable.

    Lives in `config.yaml` under `deliverable_types:`. Orc reads the list,
    matches the user request against `triggers`, then uses the matched
    template to:

    1. Pick `output_tool` and `default_theme`
    2. Build `chairman_plan` covering `required_workers` (+ optional
       `suggested_workers`) and tell each worker which `structure`
       sections their output should feed (`worker_contribution_map`)
    3. Compose the final tool call by filling the `structure` skeleton
       with worker text
    4. Pass `quality_gates` to the critic so the review is grounded in
       deliverable-specific criteria, not generic prose
    """

    id: str
    name: str = ""
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    output_tool: str = ""               # e.g. "create_management_ppt"
    default_theme: str = ""              # passed into the tool's meta.theme
    voice: str = ""                      # tone / register guidance
    suggested_workers: list[str] = Field(default_factory=list)
    required_workers: list[str] = Field(default_factory=list)
    structure: list[DeliverableSection] = Field(default_factory=list)
    worker_contribution_map: dict[str, list[str]] = Field(default_factory=dict)
    quality_gates: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


class KnowledgeBaseConfig(BaseModel):
    """One registered external knowledge base.

    `retriever` is a string id that maps to a class in
    `knowledge.retriever` (e.g. "noop", future: "chroma", "http").
    """

    id: str
    name: str = ""
    description: str = ""
    retriever: str = "noop"
    config: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 18900


class AppConfig(BaseModel):
    config_version: int = 1
    models: list[ModelConfig] = Field(default_factory=list)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    lead_agent: LeadAgentConfig = Field(default_factory=LeadAgentConfig)
    summarization: SummarizationConfig = Field(default_factory=SummarizationConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    title: TitleConfig = Field(default_factory=TitleConfig)
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    knowledge_bases: list[KnowledgeBaseConfig] = Field(default_factory=list)
    deliverable_types: list[DeliverableTypeConfig] = Field(default_factory=list)

    class Config:
        extra = "allow"

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        if config_path:
            p = Path(config_path)
            if not p.exists():
                raise FileNotFoundError(f"Config not found: {p}")
            return p
        env_path = os.getenv("BOXCC_CONFIG_PATH")
        if env_path:
            p = Path(env_path)
            if not p.exists():
                raise FileNotFoundError(f"Config from env not found: {p}")
            return p
        for base in [Path.cwd(), Path.cwd().parent]:
            p = base / "config.yaml"
            if p.exists():
                return p
        raise FileNotFoundError("config.yaml not found in CWD or parent directory")

    @classmethod
    def resolve_env_variables(cls, config: Any) -> Any:
        if isinstance(config, str):
            if config.startswith("$"):
                val = os.getenv(config[1:])
                if val is None:
                    logger.warning(f"Env var {config[1:]} not set, using empty string")
                    return ""
                return val
            return config
        if isinstance(config, dict):
            return {k: cls.resolve_env_variables(v) for k, v in config.items()}
        if isinstance(config, list):
            return [cls.resolve_env_variables(item) for item in config]
        return config

    @classmethod
    def from_file(cls, config_path: str | None = None) -> Self:
        resolved = cls.resolve_config_path(config_path)
        env_file = resolved.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        with open(resolved, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data = cls.resolve_env_variables(data)
        return cls.model_validate(data)

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((m for m in self.models if m.name == name), None)

    def get_enabled_agents(self) -> list[AgentConfig]:
        """All enabled agents including critic."""
        return [a for a in self.agents.registry if a.enabled]

    def get_worker_agents(self) -> list[AgentConfig]:
        """Enabled agents excluding `crt` — those orc can put into chairman_plan."""
        return [a for a in self.agents.registry if a.enabled and a.id != "crt"]

    def get_critic_agent(self) -> AgentConfig | None:
        """Return the critic agent if present."""
        return next((a for a in self.agents.registry if a.id == "crt"), None)

    # ---- Legacy aliases (one-release back-compat) ----
    def get_enabled_departments(self) -> list[AgentConfig]:  # noqa: D401 - shim
        return self.get_enabled_agents()


_config: AppConfig | None = None
_config_path: Path | None = None
_config_mtime: float | None = None


def get_app_config() -> AppConfig:
    global _config, _config_path, _config_mtime
    resolved = AppConfig.resolve_config_path()
    try:
        current_mtime = resolved.stat().st_mtime
    except OSError:
        current_mtime = None

    if _config is None or _config_path != resolved or _config_mtime != current_mtime:
        if _config is not None and _config_mtime != current_mtime:
            logger.info("Config file changed, reloading")
        _config = AppConfig.from_file(str(resolved))
        _config_path = resolved
        _config_mtime = current_mtime
    return _config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    global _config, _config_path, _config_mtime
    resolved = AppConfig.resolve_config_path(config_path)
    _config = AppConfig.from_file(str(resolved))
    _config_path = resolved
    _config_mtime = resolved.stat().st_mtime
    return _config