"""Memory middleware - injects memory into context and queues updates.

Memory is injected as TWO SystemMessages, in this order:

    <memory:core>   ← stable user/history summary block
    <memory:facts>  ← append-only chronological facts block

Splitting the block keeps the high-stability "core profile" cached even
when new facts arrive (the core SystemMessage is byte-identical across
turns while facts are growing). This matters for providers that cache on
the byte-exact prefix (DeepSeek, OpenAI, Kimi).
"""

import logging
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from agents.memory.prompt import format_memory_core, format_memory_facts
from agents.memory.queue import get_memory_queue
from agents.memory.updater import get_memory_data
from config.app_config import get_app_config

logger = logging.getLogger(__name__)


class MemoryMiddleware(AgentMiddleware[AgentState]):
    """Injects long-term memory before model calls, queues updates after."""

    def _inject_memory(self, state: AgentState) -> dict | None:
        """Inject memory as two stable SystemMessages (core + facts)."""
        config = get_app_config()
        if not config.memory.enabled or not config.memory.max_injection_tokens:
            return None

        memory = get_memory_data()
        if not memory:
            return None

        # Core block — stable across turns. Cache-friendly.
        core = format_memory_core(memory)
        # Facts block — append-only chronological. Suffix changes only when
        # new facts appended; prefix stays stable.
        facts = format_memory_facts(
            memory,
            max_tokens=config.memory.max_injection_tokens,
            max_facts=getattr(config.memory, "max_facts", 100),
        )

        messages: list[SystemMessage] = []
        if core:
            messages.append(SystemMessage(content="<memory:core>\n" + core + "\n</memory:core>"))
        if facts:
            messages.append(SystemMessage(content="<memory:facts>\n" + facts + "\n</memory:facts>"))

        if not messages:
            return None
        return {"messages": messages}

    def _get_thread_id(self, runtime: Runtime | None) -> str | None:
        context = getattr(runtime, "context", None) if runtime is not None else None
        if isinstance(context, dict):
            return context.get("thread_id")
        return None

    def _queue_update(self, state: AgentState, runtime: Runtime | None) -> None:
        """Queue conversation for async memory update."""
        config = get_app_config()
        if not config.memory.enabled:
            return

        thread_id = self._get_thread_id(runtime)
        if not thread_id:
            logger.debug("Skip memory update because runtime thread_id is missing")
            return

        messages = state.get("messages", [])
        if not messages:
            return

        filtered = []
        for msg in messages:
            msg_type = getattr(msg, "type", None)
            if msg_type == "human":
                filtered.append(msg)
            elif msg_type == "ai" and not getattr(msg, "tool_calls", None):
                filtered.append(msg)

        user_msgs = [m for m in filtered if getattr(m, "type", None) == "human"]
        ai_msgs = [m for m in filtered if getattr(m, "type", None) == "ai"]
        if user_msgs and ai_msgs:
            get_memory_queue().add(thread_id=thread_id, messages=filtered)

    @override
    def before_model(self, state, runtime):
        return self._inject_memory(state)

    @override
    async def abefore_model(self, state, runtime):
        return self._inject_memory(state)

    @override
    def after_agent(self, state, runtime):
        self._queue_update(state, runtime)
        return None

    @override
    async def aafter_agent(self, state, runtime):
        self._queue_update(state, runtime)
        return None
