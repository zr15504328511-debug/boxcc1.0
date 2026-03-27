"""Subagent executor - parallel department execution engine.

Simplified from DeerFlow's SubagentExecutor for boxcc's department-based architecture.
Departments run as independent LangGraph agents in parallel using asyncio.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from agents.middlewares.tool_error_middleware import ToolErrorMiddleware
from agents.thread_state import ThreadState
from config.app_config import get_app_config
from models.factory import create_chat_model
from runtime_events import current_session_id, emit_run_step
from subagents.config import SubagentConfig
from subagents.prompt import build_department_system_prompt
from session.checklist import append_artifact, emit_checklist_sync, update_checklist_item, upsert_worker_shard
from session.store import get_session_store
from subagents.task_packet import WorkerTaskPacket, render_task_packet

logger = logging.getLogger(__name__)


@dataclass
class DepartmentResult:
    id: str
    name: str
    display_name: str
    status: str = 'pending'
    content: str = ''
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


_WORKER_RUNNING_TITLES = {
    'dom': '\u5b66\u672f\u90e8\u6536\u5230\u4efb\u52a1\u5f00\u59cb\u5206\u6790',
    'pln': '\u4f01\u5212\u90e8\u8fdb\u884c\u5206\u6790\u4e2d',
    'ana': '\u7ecf\u8425\u90e8\u6b63\u5728\u6838\u7b97\u5173\u952e\u7ecf\u8425\u6307\u6807',
    'cpy': '\u5ba3\u4f20\u90e8\u6b63\u5728\u6574\u7406\u8868\u8fbe\u4e0e\u8f93\u51fa\u7ed3\u6784',
    'crt': '\u95ee\u9898\u5df2\u6574\u5408\u5230\u8d28\u68c0\u90e8\u8fdb\u884c\u8bc4\u4f30',
}


def _create_department_agent(dept: SubagentConfig, parent_model_name: str | None = None):
    model_name = parent_model_name if dept.model == 'inherit' else dept.model
    model = create_chat_model(name=model_name)

    return create_agent(
        model=model,
        tools=[],
        middleware=[ToolErrorMiddleware()],
        system_prompt=build_department_system_prompt(dept),
        state_schema=ThreadState,
    )


def _clean_inline(text: str | None, limit: int = 120) -> str:
    cleaned = ' '.join(str(text or '').split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + '...'


def _extract_previous_worker_shard(session_id: str | None, dept_id: str):
    if not session_id or dept_id == 'crt':
        return None
    state = get_session_store().get(session_id)
    if state is None:
        return None
    return state.worker_shards.get(dept_id)


def _build_worker_shard_brief(shard, packet: WorkerTaskPacket) -> str:
    if shard is None:
        return ''

    lines: list[str] = []
    status = str(getattr(shard, 'status', '') or '').strip()
    if status and status not in {'idle', 'running'}:
        lines.append(f'- Previous status: {status}')

    previous_packet = getattr(shard, 'current_task_packet', {}) or {}
    previous_task = str(previous_packet.get('task') or previous_packet.get('objective') or '').strip()
    if previous_task and previous_task != packet.task:
        lines.append(f'- Previous assignment: {_clean_inline(previous_task, limit=140)}')

    result_summary = str(getattr(shard, 'result_summary', '') or '').strip()
    latest_output = str(getattr(shard, 'latest_output', '') or '').strip()
    if result_summary:
        lines.append(f'- Previous result summary: {_clean_inline(result_summary, limit=160)}')
    elif latest_output:
        lines.append(f'- Previous output excerpt: {_clean_inline(latest_output, limit=160)}')

    validation_feedback = str(getattr(shard, 'validation_feedback', '') or '').strip()
    if validation_feedback:
        lines.append(f'- Open critic feedback: {_clean_inline(validation_feedback, limit=160)}')

    retry_count = int(getattr(shard, 'retry_count', 0) or 0)
    if retry_count:
        lines.append(f'- Retry count so far: {retry_count}')

    if not lines:
        return ''

    return (
        'Worker Session Shard\n'
        'Use this as compressed continuation memory from the same conversation. '
        'It is prior execution state for this department, not a new user request.\n'
        + '\n'.join(lines)
    )


def _build_department_request(dept: SubagentConfig, packet: WorkerTaskPacket, shard_brief: str = '') -> str:
    rendered_packet = render_task_packet(packet, dept.skill_packs)
    sections = [
        'You are receiving a single-use department task packet.',
        rendered_packet,
    ]
    if shard_brief:
        sections.append(shard_brief)
    sections.append('You do not have access to the original user prompt beyond what is included above. Execute only this assignment.')
    return '\n\n'.join(sections)


def _build_department_running_title(dept: SubagentConfig, packet: WorkerTaskPacket, *, step_suffix: str = '') -> str:
    if step_suffix.startswith('rework'):
        return f"{dept.display_name or dept.name}根据质检意见返工中"
    if dept.id == 'cpy' and 'ppt_outline' in packet.requested_skill_packs:
        return '\u5ba3\u4f20\u90e8\u6b63\u5728\u5236\u4f5cPPT\u7ed3\u6784'
    return _WORKER_RUNNING_TITLES.get(dept.id, f"{dept.display_name or dept.name}\u6b63\u5728\u6267\u884c\u4efb\u52a1")


def _build_department_running_summary(packet: WorkerTaskPacket) -> str:
    return _clean_inline(packet.task or packet.objective, limit=96)


async def _run_department(
    dept: SubagentConfig,
    packet: WorkerTaskPacket,
    parent_model_name: str | None = None,
    timeout: int = 1800,
    step_suffix: str = '',
) -> DepartmentResult:
    phase = 'critic' if dept.id == 'crt' else 'worker'
    suffix = f'_{step_suffix}' if step_suffix else ''
    step_id = f'{dept.id}_execution{suffix}'
    result = DepartmentResult(
        id=dept.id,
        name=dept.name,
        display_name=dept.display_name or dept.id,
        status='running',
        started_at=datetime.now(),
    )

    session_id = current_session_id()
    previous_shard = _extract_previous_worker_shard(session_id, dept.id)
    shard_brief = _build_worker_shard_brief(previous_shard, packet)
    checklist_item_id = 'critic_review' if dept.id == 'crt' else f'worker_{dept.id}'

    await emit_run_step(
        step_id=step_id,
        phase=phase,
        agent_id=dept.id,
        status='running',
        title=_build_department_running_title(dept, packet, step_suffix=step_suffix),
        summary=_build_department_running_summary(packet),
    )

    if session_id:
        state = upsert_worker_shard(
            session_id,
            dept.id,
            task_packet=packet.model_dump(),
            result_summary=packet.task or packet.objective,
            status='running',
        )
        state = update_checklist_item(
            session_id,
            checklist_item_id,
            status='running',
            result_preview=packet.task or packet.objective,
        )
        await emit_checklist_sync(state)

    try:
        agent = _create_department_agent(dept, parent_model_name)
        state = {'messages': [HumanMessage(content=_build_department_request(dept, packet, shard_brief=shard_brief))]}
        config = {'recursion_limit': dept.max_turns}

        final_state = await asyncio.wait_for(
            agent.ainvoke(state, config=config),
            timeout=timeout,
        )

        messages = final_state.get('messages', [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content
                if isinstance(content, str):
                    result.content = content
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict) and 'text' in block:
                            parts.append(block['text'])
                    result.content = '\n'.join(parts)
                else:
                    result.content = str(content)
                break

        result.status = 'completed'
        await emit_run_step(
            step_id=step_id,
            phase=phase,
            agent_id=dept.id,
            status='completed',
            title=_build_department_running_title(dept, packet, step_suffix=step_suffix),
            summary=_clean_inline(result.content or packet.objective, limit=110),
        )
        if session_id:
            state = upsert_worker_shard(
                session_id,
                dept.id,
                task_packet=packet.model_dump(),
                latest_output=result.content,
                result_summary=result.content or packet.objective,
                status='completed',
            )
            state = update_checklist_item(
                session_id,
                checklist_item_id,
                status='done',
                result_preview=result.content or packet.objective,
                result_ref=dept.id,
            )
            state = append_artifact(
                session_id,
                owner=dept.id,
                kind='worker_output' if dept.id != 'crt' else 'critic_output',
                content=result.content,
                linked_checklist_item=checklist_item_id,
            )
            await emit_checklist_sync(state)

    except asyncio.TimeoutError:
        logger.error('Department %s timed out after %ss', dept.name, timeout)
        result.status = 'timed_out'
        result.error = f'Timed out after {timeout}s'
        await emit_run_step(
            step_id=step_id,
            phase=phase,
            agent_id=dept.id,
            status='failed',
            title=f"{dept.display_name or dept.name}\u6267\u884c\u8d85\u65f6",
            summary=result.error,
        )
    except Exception as e:
        logger.exception('Department %s failed', dept.name)
        result.status = 'failed'
        result.error = str(e)
        await emit_run_step(
            step_id=step_id,
            phase=phase,
            agent_id=dept.id,
            status='failed',
            title=f"{dept.display_name or dept.name}\u6267\u884c\u5931\u8d25",
            summary=_clean_inline(result.error, limit=110),
        )

    result.completed_at = datetime.now()
    return result


async def run_single_department(
    dept_id: str,
    task: str,
    parent_model_name: str | None = None,
    task_packet: WorkerTaskPacket | None = None,
    step_suffix: str = '',
) -> DepartmentResult:
    from subagents.registry import get_department_config

    config = get_app_config()
    dept = get_department_config(dept_id)
    if dept is None:
        return DepartmentResult(
            id=dept_id,
            name=dept_id,
            display_name=dept_id,
            status='failed',
            error=f"Department '{dept_id}' not found",
        )
    packet = task_packet or WorkerTaskPacket(
        objective='Review and pressure-test the assembled department outputs.',
        task=task,
        required_output=['Decision', 'Conflicts', 'Risk assessment', 'Required fixes'],
        success_criteria=['Cover the major conflicts and risks', 'End with a clear go/no-go style recommendation'],
        priority='high',
    )
    return await _run_department(
        dept,
        packet,
        parent_model_name=parent_model_name,
        timeout=config.departments.timeout_seconds,
        step_suffix=step_suffix,
    )


async def run_departments(
    department_ids: list[str],
    tasks: dict[str, WorkerTaskPacket],
    parent_model_name: str | None = None,
) -> list[DepartmentResult]:
    from subagents.registry import get_department_config

    config = get_app_config()
    max_concurrent = config.departments.max_concurrent
    timeout = config.departments.timeout_seconds

    jobs = []
    for dept_id in department_ids:
        dept = get_department_config(dept_id)
        if dept is None:
            logger.warning("Department '%s' not found, skipping", dept_id)
            continue
        packet = tasks.get(dept_id)
        if packet is None:
            logger.warning("Department '%s' missing task packet, skipping", dept_id)
            continue
        jobs.append((dept, packet))

    if not jobs:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_run(dept, packet):
        async with semaphore:
            return await _run_department(
                dept,
                packet,
                parent_model_name=parent_model_name,
                timeout=timeout,
            )

    results = await asyncio.gather(
        *[bounded_run(dept, packet) for dept, packet in jobs],
        return_exceptions=True,
    )

    final_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            dept = jobs[i][0]
            final_results.append(DepartmentResult(
                id=dept.id,
                name=dept.name,
                display_name=dept.display_name,
                status='failed',
                error=str(r),
                completed_at=datetime.now(),
            ))
        else:
            final_results.append(r)

    return final_results
