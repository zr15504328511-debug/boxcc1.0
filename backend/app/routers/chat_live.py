"""Chat endpoint - core chat API using Lead Agent with timeline and streaming support."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.lead_agent import make_lead_agent
from config.app_config import AppConfig
from models.factory import reset_runtime_model, set_runtime_model
from session.checklist import build_orc_session_brief, emit_checklist_sync, set_final_summary, update_checklist_item
from session.store import get_session_store
from runtime_events import emit_run_step, reset_event_emitter, set_event_emitter
from subagents.tools import _build_routing_policy

logger = logging.getLogger(__name__)
router = APIRouter()
_agent_cache: dict[str, object] = {}
_agent_cache_config_signature: str | None = None


class RuntimeModelRequest(BaseModel):
    provider: str
    model_name: str
    api_key: str
    base_url: str = ''
    temperature: float = 0.7
    max_tokens: int = 8192


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model_name: str | None = None
    runtime_model: RuntimeModelRequest | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    ok: bool = True
    message: dict[str, Any]
    title: str | None = None
    department_results: list[dict[str, Any]] | None = None
    workflow_artifact: dict[str, Any] | None = None


def _config_signature() -> str:
    resolved = AppConfig.resolve_config_path()
    return f'{resolved}:{resolved.stat().st_mtime_ns}'


def _cache_key(model_name: str | None = None, runtime_model: RuntimeModelRequest | None = None) -> str:
    return f'runtime::{runtime_model.model_dump_json()}' if runtime_model is not None else (model_name or '__default__')


def _get_agent(model_name: str | None = None, runtime_model: RuntimeModelRequest | None = None):
    global _agent_cache_config_signature
    signature = _config_signature()
    if _agent_cache_config_signature != signature:
        _agent_cache.clear()
        _agent_cache_config_signature = signature
    cache_key = _cache_key(model_name=model_name, runtime_model=runtime_model)
    if cache_key not in _agent_cache:
        _agent_cache[cache_key] = make_lead_agent(model_name=model_name, runtime_model=runtime_model.model_dump() if runtime_model else None)
    return _agent_cache[cache_key]


def _extract_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get('text'), str):
                parts.append(block['text'])
        return '\n'.join(parts)
    return str(content) if content else ''


def _extract_delegate_artifact(messages: list[Any]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if getattr(msg, 'type', None) == 'tool' and getattr(msg, 'name', None) == 'delegate_to_departments':
            artifact = getattr(msg, 'artifact', None)
            if isinstance(artifact, dict):
                return artifact
    return None


def _extract_department_results(messages: list[Any]) -> list[dict[str, Any]] | None:
    artifact = _extract_delegate_artifact(messages)
    return artifact.get('department_results') if isinstance(artifact, dict) and isinstance(artifact.get('department_results'), list) else None


def _extract_assistant_content(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if getattr(msg, 'type', None) == 'ai' and getattr(msg, 'content', None):
            return _extract_content(msg.content)
    return ''


def _requires_department_work(routing_policy) -> bool:
    return routing_policy.category != 'direct_answer' and routing_policy.max_workers > 0


def _suggested_workers_for_policy(routing_policy) -> list[str]:
    if routing_policy.category == 'orc_selected':
        return []
    return list(dict.fromkeys([*routing_policy.required_workers, *routing_policy.allowed_workers]))[: max(0, routing_policy.max_workers)]


def _build_guarded_agent_input(agent_input: str, routing_policy) -> str:
    if not _requires_department_work(routing_policy):
        return agent_input

    guard = (
        f"<mandatory_routing_contract>\n"
        f"This request is not a tiny direct answer. You must decide which workers are necessary from the dynamic roster and call `delegate_to_departments`.\n"
        f"- Available workers: {', '.join(routing_policy.allowed_workers) or 'none'}.\n"
        f"- Do not include `crt`; critic review is automatic.\n"
        f"- Worker count is not capped, but every selected worker must add distinct value.\n"
        f"- Build `selection_rationale` first with free-text task domains and why each worker is selected.\n"
        f"- `selection_rationale.selected_workers`, `chairman_plan` keys, and `checklist_self_check.selected_workers` must match.\n"
        f"- Then immediately call `delegate_to_departments` in this turn.\n"
        f"- Do not answer with a prose routing plan; without the tool artifact, this run is invalid.\n"
        f"</mandatory_routing_contract>\n\n"
    )
    return guard + agent_input


def _chunk_text(text: str, chunk_size: int = 56) -> list[str]:
    normalized = str(text or '')
    if not normalized:
        return []
    blocks = re.split(r'(\n+)', normalized)
    chunks: list[str] = []
    for block in blocks:
        if not block:
            continue
        if block.startswith('\n'):
            chunks.append(block)
            continue
        remaining = block
        while len(remaining) > chunk_size:
            cut = remaining[:chunk_size]
            split_at = max(cut.rfind('?'), cut.rfind('?'), cut.rfind('?'), cut.rfind('. '), cut.rfind('; '), cut.rfind('?'), cut.rfind(', '))
            split_at = chunk_size if split_at <= 8 else split_at + 1
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:]
        if remaining:
            chunks.append(remaining)
    return [chunk for chunk in chunks if chunk]


def _build_agent_user_input(req: ChatRequest) -> str:
    state = get_session_store().get_or_create(req.session_id, user_goal=req.message)
    summary = build_orc_session_brief(state, current_user_message=req.message)
    return summary or req.message


async def _invoke_agent_once(agent, agent_input: str, req: ChatRequest) -> tuple[dict[str, Any], list[Any], str, dict[str, Any] | None, list[dict[str, Any]] | None]:
    result = await agent.ainvoke({'messages': [HumanMessage(content=agent_input)]}, config={'configurable': {'thread_id': req.session_id}})
    messages = result.get('messages', [])
    workflow_artifact = _extract_delegate_artifact(messages)
    department_results = _extract_department_results(messages)
    return result, messages, _extract_assistant_content(messages), workflow_artifact, department_results


async def _run_chat(req: ChatRequest, *, message_id: str | None = None) -> tuple[dict[str, Any], str | None, list[dict[str, Any]] | None, dict[str, Any] | None]:
    routing_policy = _build_routing_policy(req.message)
    requires_department_work = _requires_department_work(routing_policy)
    base_agent_input = _build_agent_user_input(req)
    agent_input = _build_guarded_agent_input(base_agent_input, routing_policy)
    token = set_runtime_model(req.runtime_model.model_dump() if req.runtime_model else None)
    try:
        agent = _get_agent(model_name=req.model_name, runtime_model=req.runtime_model)
        result, _messages, assistant_content, workflow_artifact, department_results = await _invoke_agent_once(agent, agent_input, req)
        if requires_department_work and not department_results:
            raise RuntimeError(
                f"Orc did not satisfy the mandatory routing contract for route '{routing_policy.category}': "
                "delegate_to_departments was not called, so no final answer was delivered."
            )
        set_final_summary(req.session_id, assistant_content, status='completed')
        return ({'id': message_id or str(uuid.uuid4()), 'role': 'assistant', 'content': assistant_content, 'createdAt': datetime.now(timezone.utc).isoformat()}, result.get('title'), department_results, workflow_artifact)
    finally:
        reset_runtime_model(token)


@router.post('/chat')
async def send_chat(req: ChatRequest):
    if req.stream:
        return StreamingResponse(_stream_chat(req), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
    try:
        message, title, department_results, workflow_artifact = await _run_chat(req)
        return ChatResponse(message=message, title=title, department_results=department_results, workflow_artifact=workflow_artifact)
    except Exception as e:
        logger.error('Chat error: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _stream_chat(req: ChatRequest):
    message_id = str(uuid.uuid4())
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def emitter(event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault('message_id', message_id)
        await queue.put(payload)

    async def runner() -> None:
        tokens = set_event_emitter(emitter, message_id=message_id, session_id=req.session_id)
        try:
            await emit_run_step(step_id='orc_started', phase='orc', agent_id='orc', status='running', title='主席团收到问题，正在分析派发任务', summary='正在判断问题类型、需要的部门，以及本轮任务拆分方式。')
            message, title, department_results, workflow_artifact = await _run_chat(req, message_id=message_id)
            state = get_session_store().get_or_create(req.session_id, user_goal=req.message)
            if any(item.item_id == 'orc_final' for item in state.execution_checklist):
                state = update_checklist_item(req.session_id, 'orc_final', status='done', result_preview=message.get('content', ''))
                await emit_checklist_sync(state)
            await emit_run_step(step_id='orc_finalizing', phase='final', agent_id='orc', status='completed', title='主席团已完成整合，准备返回结果', summary='最终答案已经准备就绪，正在发送给用户。')
            final_content = message.get('content', '')
            for chunk in _chunk_text(final_content):
                await queue.put({'type': 'answer_delta', 'message_id': message_id, 'delta': chunk})
                await queue.put({'type': 'node_output_delta', 'message_id': message_id, 'node_id': 'final:answer', 'step_id': 'orc_final_answer', 'phase': 'final', 'agent_id': 'orc', 'delta': chunk})
            await queue.put({'type': 'node_output_done', 'message_id': message_id, 'node_id': 'final:answer', 'step_id': 'orc_final_answer', 'phase': 'final', 'agent_id': 'orc', 'status': 'completed', 'content': final_content, 'error': None})
            await queue.put({'type': 'done', 'message_id': message_id, 'message': message, 'title': title, 'department_results': department_results, 'workflow_artifact': workflow_artifact})
        except Exception as exc:
            logger.error('Stream error: %s', exc, exc_info=True)
            state = update_checklist_item(req.session_id, 'orc_final', status='failed', result_preview=str(exc))
            await emit_checklist_sync(state)
            await queue.put({'type': 'node_output_done', 'message_id': message_id, 'node_id': 'final:answer', 'step_id': 'orc_final_answer', 'phase': 'final', 'agent_id': 'orc', 'status': 'failed', 'content': '', 'error': str(exc)})
            await queue.put({'type': 'error', 'message_id': message_id, 'error': str(exc)})
        finally:
            reset_event_emitter(tokens)
            await queue.put({'type': 'stream_closed'})

    task = asyncio.create_task(runner())
    try:
        while True:
            event = await queue.get()
            if event.get('type') == 'stream_closed':
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        await task
