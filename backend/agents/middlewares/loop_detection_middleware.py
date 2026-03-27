"""Loop detection middleware - detects and breaks repetitive tool call loops.

Adapted from DeerFlow's LoopDetectionMiddleware.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict, defaultdict
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_WARNING_MSG = (
    "[Loop warning] You are repeating the same tool call. "
    "Stop calling tools and answer with the information you already have."
)

_HARD_STOP_MSG = (
    "[Forced stop] Repeated tool calls exceeded the safety limit. "
    "Answer immediately with the information already collected."
)


def _hash_tool_calls(tool_calls: list[dict]) -> str:
    normalized = sorted(
        [{"name": tc.get("name", ""), "args": tc.get("args", {})} for tc in tool_calls],
        key=lambda tc: (tc["name"], json.dumps(tc["args"], sort_keys=True, default=str)),
    )
    blob = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]


class LoopDetectionMiddleware(AgentMiddleware[AgentState]):
    def __init__(self, warn_threshold: int = 3, hard_limit: int = 5, window_size: int = 20):
        super().__init__()
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self._lock = threading.Lock()
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)

    def _get_thread_id(self, runtime: Runtime | None) -> str:
        context = getattr(runtime, "context", None) if runtime is not None else None
        if isinstance(context, dict):
            return context.get("thread_id", "default")
        return "default"

    def _track_and_check(self, state: AgentState, runtime: Runtime | None) -> tuple[str | None, bool]:
        messages = state.get("messages", [])
        if not messages:
            return None, False

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None, False

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None, False

        thread_id = self._get_thread_id(runtime)
        call_hash = _hash_tool_calls(tool_calls)

        with self._lock:
            if thread_id in self._history:
                self._history.move_to_end(thread_id)
            else:
                self._history[thread_id] = []

            history = self._history[thread_id]
            history.append(call_hash)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size:]

            count = history.count(call_hash)

            if count >= self.hard_limit:
                logger.error("Loop hard limit reached for thread %s", thread_id)
                return _HARD_STOP_MSG, True

            if count >= self.warn_threshold and call_hash not in self._warned[thread_id]:
                self._warned[thread_id].add(call_hash)
                logger.warning("Loop warning for thread %s (count=%d)", thread_id, count)
                return _WARNING_MSG, False

        return None, False

    def _apply(self, state: AgentState, runtime: Runtime | None) -> dict | None:
        warning, hard_stop = self._track_and_check(state, runtime)

        if hard_stop:
            messages = state.get("messages", [])
            last_msg = messages[-1]
            stripped = last_msg.model_copy(update={
                "tool_calls": [],
                "content": (last_msg.content or "") + f"\n\n{_HARD_STOP_MSG}",
            })
            return {"messages": [stripped]}

        if warning:
            return {"messages": [SystemMessage(content=warning)]}

        return None

    @override
    def after_model(self, state, runtime):
        return self._apply(state, runtime)

    @override
    async def aafter_model(self, state, runtime):
        return self._apply(state, runtime)
