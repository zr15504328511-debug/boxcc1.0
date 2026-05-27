"""Model factory - create LangChain chat models from config or runtime profile."""

import importlib
import logging
from contextvars import ContextVar, Token
from typing import Any

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from config.app_config import ModelConfig, get_app_config

logger = logging.getLogger(__name__)

_runtime_model_var: ContextVar[dict[str, Any] | None] = ContextVar("runtime_model", default=None)


class RuntimeModelConfig(BaseModel):
    provider: str
    model_name: str
    api_key: str
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192


def resolve_class(use_path: str, base_class: type = object) -> type:
    """Resolve a class from 'module:ClassName' string."""
    if ":" not in use_path:
        raise ValueError(f"Invalid use path '{use_path}', expected 'module:ClassName'")
    module_path, class_name = use_path.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Cannot import module '{module_path}': {e}") from e
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"Class '{class_name}' not found in module '{module_path}'")
    if not issubclass(cls, base_class):
        raise TypeError(f"'{class_name}' is not a subclass of {base_class.__name__}")
    return cls


def set_runtime_model(config: dict[str, Any] | RuntimeModelConfig | None) -> Token:
    if config is None:
        return _runtime_model_var.set(None)
    if isinstance(config, RuntimeModelConfig):
        payload = config.model_dump()
    else:
        payload = RuntimeModelConfig.model_validate(config).model_dump()
    return _runtime_model_var.set(payload)


def reset_runtime_model(token: Token) -> None:
    _runtime_model_var.reset(token)


def get_runtime_model() -> dict[str, Any] | None:
    return _runtime_model_var.get()


def _build_runtime_model(runtime_model: dict[str, Any] | RuntimeModelConfig, **kwargs) -> BaseChatModel:
    runtime = runtime_model if isinstance(runtime_model, RuntimeModelConfig) else RuntimeModelConfig.model_validate(runtime_model)
    provider = runtime.provider.strip()

    if provider in {"OpenAI", "OpenRouter", "Custom"}:
        model_class = resolve_class("langchain_openai:ChatOpenAI", BaseChatModel)
        settings = {
            "model_name": runtime.model_name,
            "openai_api_key": runtime.api_key,
            "temperature": runtime.temperature,
            "max_tokens": runtime.max_tokens,
        }
        if runtime.base_url:
            settings["openai_api_base"] = runtime.base_url
        settings.update(kwargs)
        logger.info("Creating runtime OpenAI-compatible model provider=%s model=%s", provider, runtime.model_name)
        return model_class(**settings)

    if provider == "Anthropic":
        model_class = resolve_class("langchain_anthropic:ChatAnthropic", BaseChatModel)
        settings = {
            "model": runtime.model_name,
            "anthropic_api_key": runtime.api_key,
            "temperature": runtime.temperature,
            "max_tokens": runtime.max_tokens,
        }
        if runtime.base_url:
            settings["base_url"] = runtime.base_url
        settings.update(kwargs)
        logger.info("Creating runtime Anthropic model=%s", runtime.model_name)
        return model_class(**settings)

    raise ValueError(f"Provider '{provider}' is not supported for runtime chat yet")


def extract_cache_usage(usage: dict[str, Any] | None) -> dict[str, int]:
    """Normalise prompt-cache telemetry across providers.

    Returns ``{"hit": int, "miss": int, "prompt": int, "completion": int}``
    where missing fields default to 0. Handles three field shapes:

    * **DeepSeek** — ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``
      with ``prompt_tokens = hit + miss``.
    * **OpenAI-compatible** (OpenAI, Kimi, most Qwen via DashScope) —
      ``prompt_tokens_details.cached_tokens`` is the hit; miss is derived.
    * **Anthropic** — ``cache_read_input_tokens`` (hit) and
      ``cache_creation_input_tokens`` (write, billed as miss in this view).

    Callers can compute hit ratio as ``hit / max(prompt, 1)``.
    """
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)

    # DeepSeek extension wins if present (explicit hit/miss split).
    ds_hit = usage.get("prompt_cache_hit_tokens")
    ds_miss = usage.get("prompt_cache_miss_tokens")
    if ds_hit is not None or ds_miss is not None:
        hit = int(ds_hit or 0)
        miss = int(ds_miss or 0) or max(prompt - hit, 0)
        if not prompt:
            prompt = hit + miss
        return {"hit": hit, "miss": miss, "prompt": prompt, "completion": completion}

    # OpenAI shape: prompt_tokens_details.cached_tokens
    details = usage.get("prompt_tokens_details") or usage.get("input_token_details") or {}
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        hit = int(details.get("cached_tokens") or 0)
        miss = max(prompt - hit, 0)
        return {"hit": hit, "miss": miss, "prompt": prompt, "completion": completion}

    # Anthropic shape: cache_read_input_tokens + cache_creation_input_tokens
    a_read = usage.get("cache_read_input_tokens")
    a_create = usage.get("cache_creation_input_tokens")
    if a_read is not None or a_create is not None:
        hit = int(a_read or 0)
        miss = int(a_create or 0)
        if not prompt:
            prompt = hit + miss
        return {"hit": hit, "miss": miss, "prompt": prompt, "completion": completion}

    # No cache telemetry exposed by this provider.
    return {"hit": 0, "miss": prompt, "prompt": prompt, "completion": completion}


def extract_cache_usage_from_messages(messages: list[Any]) -> dict[str, int]:
    """Aggregate cache usage across all AIMessages in a final state.

    LangChain exposes provider usage through ``AIMessage.usage_metadata``
    (new) and ``AIMessage.response_metadata['token_usage']`` (older). We
    sum across every assistant message in the run.
    """
    totals = {"hit": 0, "miss": 0, "prompt": 0, "completion": 0}
    for msg in messages or []:
        if getattr(msg, "type", None) != "ai":
            continue
        # Newer LangChain: usage_metadata is the canonical shape.
        meta = getattr(msg, "usage_metadata", None)
        sample: dict[str, Any] | None = None
        if isinstance(meta, dict):
            sample = {
                "prompt_tokens": meta.get("input_tokens"),
                "completion_tokens": meta.get("output_tokens"),
                "input_token_details": meta.get("input_token_details"),
            }
        response_meta = getattr(msg, "response_metadata", None) or {}
        token_usage = response_meta.get("token_usage") if isinstance(response_meta, dict) else None
        if isinstance(token_usage, dict):
            sample = {**(sample or {}), **token_usage}
        if not sample:
            continue
        chunk = extract_cache_usage(sample)
        for k in totals:
            totals[k] += chunk[k]
    return totals


def create_chat_model(name: str | None = None, runtime_model: dict[str, Any] | RuntimeModelConfig | None = None, **kwargs) -> BaseChatModel:
    """Create a chat model instance from config or runtime profile."""
    active_runtime_model = runtime_model or (get_runtime_model() if name is None else None)
    if active_runtime_model is not None:
        return _build_runtime_model(active_runtime_model, **kwargs)

    config = get_app_config()
    if not config.models:
        raise ValueError("No models configured in config.yaml")

    if name is None:
        model_config = config.models[0]
    else:
        model_config = config.get_model_config(name)
        if model_config is None:
            raise ValueError(f"Model '{name}' not found in config")

    model_class = resolve_class(model_config.use, BaseChatModel)
    settings = model_config.model_dump(
        exclude_none=True,
        exclude={"use", "name", "display_name"},
    )
    settings.update(kwargs)

    logger.info("Creating model '%s' (%s)", model_config.name, model_config.use)
    return model_class(**settings)
