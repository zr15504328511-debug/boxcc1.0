"""Inject the per-turn `<world_state>` snapshot as a SystemMessage.

Sits *before* MemoryMiddleware in the pipeline so the resulting message
order is:

    [system_prompt (boxcc.md + spec)]   ← create_agent's system_prompt
    [<world_state>]                      ← this middleware
    [<memory>]                           ← MemoryMiddleware
    [history messages]
    [user message]

The session id is resolved from the `runtime_events` contextvar
(`current_session_id()`), which `chat.py` sets at the start of every
chat request (streaming and non-streaming alike).
"""

from __future__ import annotations

import logging
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from runtime_events import current_session_id
from session.store import get_session_store
from session.world_state import render_world_state

logger = logging.getLogger(__name__)


class WorldStateMiddleware(AgentMiddleware[AgentState]):
    """Inject `<world_state>` before each model call.

    Args:
        perspective: "lead" or a worker id (e.g. "dom"). Determines which
            slice of the session state is rendered.
    """

    def __init__(self, perspective: str = "lead") -> None:
        super().__init__()
        self.perspective = perspective

    def _build(self) -> dict | None:
        session_id = current_session_id()
        if not session_id:
            return None
        try:
            state = get_session_store().get(session_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load session state for %s: %s", session_id, exc)
            return None
        rendered = render_world_state(state, perspective=self.perspective)
        if not rendered:
            return None
        return {"messages": [SystemMessage(content=rendered)]}

    @override
    def before_model(self, state, runtime):
        return self._build()

    @override
    async def abefore_model(self, state, runtime):
        return self._build()
