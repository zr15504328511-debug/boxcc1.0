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
from session.checklist import build_initial_checklist, build_orc_session_brief, emit_checklist_sync, set_final_summary, sync_session_checklist, update_checklist_item
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


async def _run_chat(req: ChatRequest, *, message_id: str | None = None) -> tuple[dict[str, Any], str | None, list[dict[str, Any]] | None, dict[str, Any] | None]:
    agent_input = _build_agent_user_input(req)
    token = set_runtime_model(req.runtime_model.model_dump() if req.runtime_model else None)
    try:
        agent = _get_agent(model_name=req.model_name, runtime_model=req.runtime_model)
        result = await agent.ainvoke({'messages': [HumanMessage(content=agent_input)]}, config={'configurable': {'thread_id': req.session_id}})
        messages = result.get('messages', [])
        assistant_content = ''
        for msg in reversed(messages):
            if getattr(msg, 'type', None) == 'ai' and getattr(msg, 'content', None):
                assistant_content = _extract_content(msg.content)
                break
        workflow_artifact = _extract_delegate_artifact(messages)
        set_final_summary(req.session_id, assistant_content, status='completed')
        return ({'id': message_id or str(uuid.uuid4()), 'role': 'assistant', 'content': assistant_content, 'createdAt': datetime.now(timezone.utc).isoformat()}, result.get('title'), _extract_department_results(messages), workflow_artifact)
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
            routing_policy = _build_routing_policy(req.message)
            suggested_workers = list(dict.fromkeys([*routing_policy.required_workers, *routing_policy.allowed_workers]))[: max(0, routing_policy.max_workers)]
            state = sync_session_checklist(
                req.session_id,
                build_initial_checklist(req.session_id, req.message, routing_policy.category, suggested_workers),
                user_goal=req.message,
                task_type=routing_policy.category,
                selected_workers=suggested_workers,
                run_status='running',
            )
            await emit_checklist_sync(state)
            await emit_run_step(step_id='orc_started', phase='orc', agent_id='orc', status='running', title='\u4e3b\u5e2d\u56e2\u6536\u5230\u95ee\u9898\uff0c\u6b63\u5728\u5206\u6790\u6d3e\u53d1\u4efb\u52a1', summary='\u6b63\u5728\u5224\u65ad\u95ee\u9898\u7c7b\u578b\u3001\u9700\u8981\u7684\u90e8\u95e8\uff0c\u4ee5\u53ca\u672c\u8f6e\u4efb\u52a1\u62c6\u5206\u65b9\u5f0f\u3002')
            message, title, department_results, workflow_artifact = await _run_chat(req, message_id=message_id)
            state = update_checklist_item(req.session_id, 'orc_final', status='done', result_preview=message.get('content', ''))
            await emit_checklist_sync(state)
            await emit_run_step(step_id='orc_finalizing', phase='final', agent_id='orc', status='completed', title='\u4e3b\u5e2d\u56e2\u5df2\u5b8c\u6210\u6574\u5408\uff0c\u51c6\u5907\u8fd4\u56de\u7ed3\u679c', summary='\u6700\u7ec8\u7b54\u6848\u5df2\u7ecf\u51c6\u5907\u5c31\u7eea\uff0c\u6b63\u5728\u53d1\u9001\u7ed9\u7528\u6237\u3002')
            for chunk in _chunk_text(message.get('content', '')):
                await queue.put({'type': 'answer_delta', 'message_id': message_id, 'delta': chunk})
            await queue.put({'type': 'done', 'message_id': message_id, 'message': message, 'title': title, 'department_results': department_results, 'workflow_artifact': workflow_artifact, 'checklist': [item.model_dump() for item in state.execution_checklist]})
        except Exception as exc:
            logger.error('Stream error: %s', exc, exc_info=True)
            state = update_checklist_item(req.session_id, 'orc_final', status='failed', result_preview=str(exc))
            await emit_checklist_sync(state)
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
