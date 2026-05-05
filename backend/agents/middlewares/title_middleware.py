"""Title middleware - auto-generate conversation titles after first exchange."""

import logging
from typing import Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware

from config.app_config import get_app_config
from models.factory import RuntimeModelConfig, create_chat_model

logger = logging.getLogger(__name__)

_TITLE_PROMPT = """Based on this conversation, generate a concise title (max {max_chars} characters).
Return ONLY the title text, no quotes or formatting.

User: {user_msg}
Assistant: {assistant_msg}

Title:"""


class TitleMiddlewareState(AgentState):
    title: NotRequired[str | None]


class TitleMiddleware(AgentMiddleware[TitleMiddlewareState]):
    state_schema = TitleMiddlewareState

    def __init__(self, runtime_model: dict[str, Any] | RuntimeModelConfig | None = None):
        self.runtime_model = runtime_model

    def _should_generate(self, state: TitleMiddlewareState) -> bool:
        config = get_app_config()
        if not config.title.enabled:
            return False
        if state.get("title"):
            return False

        messages = state.get("messages", [])
        user_msgs = [m for m in messages if m.type == "human"]
        ai_msgs = [m for m in messages if m.type == "ai"]
        return len(user_msgs) == 1 and len(ai_msgs) >= 1

    def _normalize_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(self._normalize_content(item) for item in content)
        if isinstance(content, dict):
            return content.get("text", "")
        return ""

    def _fallback_title(self, user_msg: str, max_chars: int) -> str:
        if not user_msg:
            return "未命名任务"
        truncated = user_msg[:max_chars]
        if len(user_msg) > max_chars and max_chars > 3:
            truncated = user_msg[: max_chars - 3] + "..."
        return truncated

    def _build_prompt(self, state: TitleMiddlewareState) -> tuple[str, int, str]:
        config = get_app_config()
        messages = state.get("messages", [])
        user_msg = self._normalize_content(
            next((m.content for m in messages if m.type == "human"), "")
        )[:500]
        assistant_msg = self._normalize_content(
            next((m.content for m in messages if m.type == "ai"), "")
        )[:500]
        prompt = _TITLE_PROMPT.format(
            max_chars=config.title.max_chars,
            user_msg=user_msg,
            assistant_msg=assistant_msg,
        )
        return prompt, config.title.max_chars, user_msg

    def _generate(self, state: TitleMiddlewareState) -> dict | None:
        if not self._should_generate(state):
            return None

        prompt, max_chars, user_msg = self._build_prompt(state)

        try:
            model = create_chat_model(runtime_model=self.runtime_model)
            response = model.invoke(prompt)
            title = self._normalize_content(response.content).strip().strip("\"'")
            title = title[:max_chars]
            if not title:
                title = self._fallback_title(user_msg, max_chars)
        except Exception:
            logger.exception("Failed to generate title")
            title = self._fallback_title(user_msg, max_chars)

        return {"title": title or "未命名任务"}

    async def _agenerate(self, state: TitleMiddlewareState) -> dict | None:
        if not self._should_generate(state):
            return None

        prompt, max_chars, user_msg = self._build_prompt(state)

        try:
            model = create_chat_model(runtime_model=self.runtime_model)
            response = await model.ainvoke(prompt)
            title = self._normalize_content(response.content).strip().strip("\"'")
            title = title[:max_chars]
            if not title:
                title = self._fallback_title(user_msg, max_chars)
        except Exception:
            logger.exception("Failed to generate title")
            title = self._fallback_title(user_msg, max_chars)

        return {"title": title or "未命名任务"}

    @override
    def after_model(self, state, runtime):
        return self._generate(state)

    @override
    async def aafter_model(self, state, runtime):
        return await self._agenerate(state)
