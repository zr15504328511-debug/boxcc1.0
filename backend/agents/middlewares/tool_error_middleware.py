"""Tool error handling middleware - converts tool exceptions into ToolMessages."""

import logging
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

logger = logging.getLogger(__name__)


class ToolErrorMiddleware(AgentMiddleware[AgentState]):
    """Convert tool exceptions into error ToolMessages so the agent can recover."""

    def _build_error_message(self, request: ToolCallRequest, exc: Exception) -> ToolMessage:
        tool_name = str(request.tool_call.get("name", "unknown"))
        tool_call_id = str(request.tool_call.get("id", "missing"))
        detail = str(exc).strip() or exc.__class__.__name__
        if len(detail) > 500:
            detail = detail[:497] + "..."

        return ToolMessage(
            content=f"Error: Tool '{tool_name}' failed: {detail}. Try an alternative approach.",
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

    @override
    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as exc:
            logger.exception("Tool failed (sync): %s", request.tool_call.get("name"))
            return self._build_error_message(request, exc)

    @override
    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as exc:
            logger.exception("Tool failed (async): %s", request.tool_call.get("name"))
            return self._build_error_message(request, exc)
