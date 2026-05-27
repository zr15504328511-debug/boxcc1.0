"""Lead agent factory - creates the main LangGraph agent with middleware pipeline."""

import logging

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware

from agents.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from agents.middlewares.memory_middleware import MemoryMiddleware
from agents.middlewares.title_middleware import TitleMiddleware
from agents.middlewares.tool_error_middleware import ToolErrorMiddleware
from agents.middlewares.world_state_middleware import WorldStateMiddleware
from agents.prompt import build_lead_system_prompt
from agents.thread_state import ThreadState
from config.app_config import get_app_config
from models.factory import RuntimeModelConfig, create_chat_model
from subagents.tools import delegate_to_departments
from tools import (
    create_docx,
    create_management_ppt,
    create_markdown,
    create_product_detail_page,
    create_pptx,
    create_xlsx,
)

logger = logging.getLogger(__name__)


def _build_middlewares(runtime_model: dict | RuntimeModelConfig | None = None):
    """Build the middleware pipeline for the lead agent."""
    config = get_app_config()
    middlewares = []

    # 1. Tool error handling (wraps tool calls)
    middlewares.append(ToolErrorMiddleware())

    # 2. Summarization (context window management)
    if config.summarization.enabled:
        model = create_chat_model(runtime_model=runtime_model)
        middlewares.append(SummarizationMiddleware(
            model=model,
            trigger=[("tokens", config.summarization.max_token_threshold)],
            keep=("messages", config.summarization.keep_recent_messages),
        ))

    # 3. Title generation (after first exchange)
    if config.title.enabled:
        middlewares.append(TitleMiddleware(runtime_model=runtime_model))

    # 4a. World state snapshot (per-turn working state, injected as
    #     SystemMessage before memory so message order is
    #     system_prompt → <world_state> → <memory> → history → user).
    middlewares.append(WorldStateMiddleware(perspective="lead"))

    # 4b. Memory (inject before model, queue update after agent)
    if config.memory.enabled:
        middlewares.append(MemoryMiddleware())

    # 5. Loop detection (prevent runaway tool calls)
    middlewares.append(LoopDetectionMiddleware())

    return middlewares


def make_lead_agent(model_name: str | None = None, runtime_model: dict | RuntimeModelConfig | None = None):
    """Create the lead agent with middleware pipeline.

    Args:
        model_name: Optional model name override. Uses first model from config if None.

    Returns:
        A compiled LangGraph agent.
    """
    model = create_chat_model(name=model_name, runtime_model=runtime_model)
    system_prompt = build_lead_system_prompt()
    middlewares = _build_middlewares(runtime_model=runtime_model)

    logger.info(
        "Creating lead agent with %d middleware(s), model=%s",
        len(middlewares),
        model_name or "default",
    )

    agent = create_agent(
        model=model,
        tools=[
            delegate_to_departments,
            create_management_ppt,
            create_product_detail_page,
            create_pptx,
            create_docx,
            create_xlsx,
            create_markdown,
        ],
        middleware=middlewares,
        system_prompt=system_prompt,
        state_schema=ThreadState,
    )

    return agent
