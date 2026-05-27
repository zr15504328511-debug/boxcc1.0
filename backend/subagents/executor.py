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
from agents.middlewares.world_state_middleware import WorldStateMiddleware
from agents.thread_state import ThreadState
from config.app_config import get_app_config
from knowledge.tools import query_knowledge_base, reset_kb_allowlist, set_kb_allowlist
from models.factory import create_chat_model
from runtime_events import current_session_id, current_turn_id, emit_run_step
from subagents.config import SubagentConfig
from subagents.prompt import build_department_system_prompt
from session.checklist import emit_checklist_sync, update_checklist_item, upsert_artifact, upsert_worker_shard
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
    # \u5546\u54c1\u4e2d\u5fc3
    'mer_plan': '\u5546\u54c1\u4f01\u5212\u6b63\u5728\u62c6\u89e3\u8d27\u76d8 / \u4ef7\u683c\u5e26 / \u6ce2\u6bb5',
    'mer_ops': '\u5546\u54c1\u8fd0\u8425\u6b63\u5728\u5206\u6790\u552e\u7f44 / \u52a8\u9500 / \u5e93\u9500\u6bd4',
    # \u4f9b\u5e94\u94fe\u4e2d\u5fc3
    'sup_buy': '\u91c7\u8d2d\u6b63\u5728\u8be2\u4ef7 / \u6bd4\u4ef7 / \u8bc4\u4f30\u4f9b\u5e94\u5546',
    'sup_pmc': '\u751f\u4ea7\u534f\u8c03\u6b63\u5728\u6392\u671f / \u8ddf\u5355 / \u8bc4\u4f30\u7ffb\u5355',
    'sup_qc': '\u54c1\u8d28 QC \u6b63\u5728\u5224\u5b9a\u7f3a\u9677 / \u8d77\u8349\u6574\u6539\u8981\u6c42',
    'sup_wms': '\u4ed3\u50a8\u7269\u6d41\u6b63\u5728\u6838\u67e5\u5e93\u5b58 / \u53d1\u8d27 / \u9000\u4ed3',
    # \u6e20\u9053\u4e2d\u5fc3
    'chl_ch': '\u6e20\u9053\u8fd0\u8425\u6b63\u5728\u8ddf\u56de\u6b3e / \u5904\u7406\u4e71\u4ef7 / \u8bc4\u4f30\u8ba2\u8d27',
    'chl_store': '\u95e8\u5e97\u8fd0\u8425\u6b63\u5728\u5206\u6790\u5e97\u6548 / \u5de1\u5e97 / \u9648\u5217',
    'chl_ec': '\u7535\u5546\u8fd0\u8425\u6b63\u5728\u8ddf\u6570\u636e / \u6392\u54c1 / \u8c03\u76f4\u64ad',
    # \u589e\u957f\u4e2d\u5fc3
    'gro_brand': '\u54c1\u724c\u8425\u9500\u6b63\u5728\u505a IMC / \u8425\u9500\u65e5\u5386 / \u9884\u7b97',
    'gro_pr': '\u516c\u5173\u6b63\u5728\u8bc4\u4f30\u8206\u60c5 / \u8d77\u8349\u53e3\u5f84\u4e0e\u58f0\u660e',
    'gro_content': '\u5185\u5bb9\u793e\u5a92\u6b63\u5728\u5199\u5356\u70b9 / \u811a\u672c / \u6587\u6848',
    # \u7ecf\u8425\u652f\u6301
    'biz_bi': '\u6570\u636e BI \u6b63\u5728\u62c9\u53e3\u5f84 / \u770b\u677f / \u6f0f\u6597\u5206\u6790',
    'biz_fin': '\u8d22\u52a1\u6b63\u5728\u7b97\u6210\u672c / \u6bdb\u5229 / \u8dcc\u4ef7 / \u76c8\u4e8f',
    'biz_hr': 'HR \u6b63\u5728\u5904\u7406\u62db\u8058 / \u7ee9\u6548 / \u57f9\u8bad',
    'biz_voc': '\u5ba2\u670d VOC \u6b63\u5728\u805a\u7c7b\u5ba2\u8bc9 / \u8d77\u8349\u8bdd\u672f',
    'biz_legal': '\u6cd5\u52a1\u6b63\u5728\u5ba1\u5408\u540c / \u5e7f\u544a\u6cd5 / \u5408\u89c4',
    'biz_it': 'IT \u6b63\u5728\u6392\u67e5\u63a5\u53e3 / \u4e3b\u6570\u636e / \u6743\u9650',
    # \u98ce\u63a7
    'crt': '\u95ee\u9898\u5df2\u6574\u5408\u5230\u98ce\u63a7\u90e8\u8fdb\u884c\u8bc4\u4f30',
}


def _create_department_agent(dept: SubagentConfig, parent_model_name: str | None = None):
    # Per-agent model overrides were dropped in the registry refactor; every
    # worker inherits the parent (lead) model. Re-introduce a `model:` field
    # on AgentConfig if you need per-agent model selection later.
    model = create_chat_model(name=parent_model_name)

    # WorldStateMiddleware renders the per-worker slice of OrcSessionState
    # as a SystemMessage so workers always see the canonical task state.
    # query_knowledge_base is granted to every worker; the tool itself
    # enforces per-invocation kb_refs via contextvar — see knowledge.tools.
    return create_agent(
        model=model,
        tools=[query_knowledge_base],
        middleware=[ToolErrorMiddleware(), WorldStateMiddleware(perspective=dept.id)],
        system_prompt=build_department_system_prompt(dept),
        state_schema=ThreadState,
    )


def _clean_inline(text: str | None, limit: int = 120) -> str:
    cleaned = ' '.join(str(text or '').split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + '...'


def _build_department_request(dept: SubagentConfig, packet: WorkerTaskPacket) -> str:
    # The registered KB allowlist is rendered into the packet body so the
    # worker can see which KBs it's permitted to consult (subset of orc's
    # `kb_refs` directive, intersected with the agent's declared scope).
    available_refs = list(dict.fromkeys([*dept.kb_refs, *packet.kb_refs]))
    rendered_packet = render_task_packet(packet, available_refs)
    return (
        'You are receiving a single-use agent task packet.\n\n'
        f'{rendered_packet}\n\n'
        'You do not have access to the original user conversation beyond what is included above. Execute only this assignment.'
    )


def _build_attached_history_messages(packet: WorkerTaskPacket) -> list:
    """Convert orc-curated history fragments into LangChain messages.

    These are spliced *before* the task HumanMessage so the worker sees
    a small, hand-picked excerpt of prior conversation when orc deems
    it necessary. The list is empty by default — workers stay stateless.
    """
    out: list = []
    for item in packet.attached_history:
        if item.role == 'assistant':
            out.append(AIMessage(content=item.content))
        else:
            out.append(HumanMessage(content=item.content))
    return out


def _build_department_running_title(dept: SubagentConfig, packet: WorkerTaskPacket, *, step_suffix: str = '') -> str:
    if step_suffix.startswith('rework'):
        return f"{dept.name}\u6b63\u5728\u6309\u98ce\u63a7\u53cd\u9988\u8fd4\u5de5"
    return _WORKER_RUNNING_TITLES.get(dept.id, f"{dept.name}\u6b63\u5728\u6267\u884c\u4efb\u52a1")


def _build_department_running_summary(packet: WorkerTaskPacket) -> str:
    return _clean_inline(packet.task or packet.objective, limit=96)


async def _run_department(
    dept: SubagentConfig,
    packet: WorkerTaskPacket,
    parent_model_name: str | None = None,
    timeout: int = 1800,
    step_suffix: str = '',
    attempt_number: int = 1,
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
    turn_id = current_turn_id() or ''
    checklist_item_id = 'critic_review' if dept.id == 'crt' else f'worker_{dept.id}'
    artifact_kind = 'critic_output' if dept.id == 'crt' else 'worker_output'
    artifact_id = f'{turn_id}:{dept.id}:{artifact_kind}:{attempt_number}'

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
            attempt_number=attempt_number,
        )
        state = update_checklist_item(
            session_id,
            checklist_item_id,
            status='running',
            result_preview=packet.task or packet.objective,
        )
        await emit_checklist_sync(state)

    # Compute this run's KB allowlist: intersection of the agent's
    # declared scope (dept.kb_refs) with orc's grant (packet.kb_refs).
    # If orc didn't grant any, fall back to the agent's declared scope so
    # the worker isn't artificially starved when orc forgot to specify.
    effective_kb_refs = (
        [r for r in packet.kb_refs if r in dept.kb_refs]
        if packet.kb_refs
        else list(dept.kb_refs)
    )
    kb_token = set_kb_allowlist(effective_kb_refs)
    try:
        agent = _create_department_agent(dept, parent_model_name)
        history_messages = _build_attached_history_messages(packet)
        task_message = HumanMessage(content=_build_department_request(dept, packet))
        state = {'messages': [*history_messages, task_message]}
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
                attempt_number=attempt_number,
            )
            state = update_checklist_item(
                session_id,
                checklist_item_id,
                status='done',
                result_preview=result.content or packet.objective,
                result_ref=dept.id,
            )
            state = upsert_artifact(
                session_id,
                artifact_id=artifact_id,
                owner=dept.id,
                kind=artifact_kind,
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
    finally:
        reset_kb_allowlist(kb_token)

    result.completed_at = datetime.now()
    return result


async def run_single_department(
    dept_id: str,
    task: str,
    parent_model_name: str | None = None,
    task_packet: WorkerTaskPacket | None = None,
    step_suffix: str = '',
    attempt_number: int = 1,
) -> DepartmentResult:
    from subagents.registry import get_agent_config

    config = get_app_config()
    dept = get_agent_config(dept_id)
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
        timeout=config.agents.timeout_seconds,
        step_suffix=step_suffix,
        attempt_number=attempt_number,
    )


async def run_departments(
    department_ids: list[str],
    tasks: dict[str, WorkerTaskPacket],
    parent_model_name: str | None = None,
) -> list[DepartmentResult]:
    from subagents.registry import get_agent_config

    config = get_app_config()
    max_concurrent = config.agents.max_concurrent
    timeout = config.agents.timeout_seconds

    jobs = []
    for dept_id in department_ids:
        dept = get_agent_config(dept_id)
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
