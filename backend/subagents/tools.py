"""Department delegation tool for the lead agent.

Flow: Chairman (orc) selects workers -> Worker departments run in parallel -> Critic (crt) reviews.
"""

from __future__ import annotations

import json
import logging
import re
import asyncio
from dataclasses import asdict, dataclass
from typing import Annotated, Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError

from runtime_events import current_session_id, emit_run_step
from session.checklist import append_artifact, build_initial_checklist, emit_checklist_sync, parse_validation_report, set_validation_report, sync_session_checklist, update_checklist_item, upsert_worker_shard, validate_checklist_draft, validate_checklist_self_check
from subagents.executor import run_departments, run_single_department
from subagents.registry import get_department_configs
from subagents.task_packet import WorkerTaskPacket

logger = logging.getLogger(__name__)

_SKILL_PACK_ALIASES = {
    'fabric_knowledge': 'fabric_rag',
    'garment_construction': 'fabric_rag',
    'quality_control': 'fabric_rag',
    'planning_strategy': 'calendar_planner',
    'product_development': 'sheet_builder',
    'cost_control': 'margin_modeler',
    'pricing_analysis': 'margin_modeler',
    'trend_analysis': 'trend_search',
    'market_search': 'trend_search',
}

ASCII_GREETING_MARKERS = {'hello', 'hi', 'hey', 'thanks', 'thank you', 'good morning', 'good evening'}


def _u(value: str) -> str:
    return value.encode('ascii').decode('unicode_escape')


CJK_GREETING_PATTERNS = [_u(r'\u4f60\u597d'), _u(r'\u60a8\u597d'), _u(r'\u65e9\u4e0a\u597d'), _u(r'\u4e0b\u5348\u597d'), _u(r'\u665a\u4e0a\u597d'), _u(r'\u8c22\u8c22')]


@dataclass
class RoutingPolicy:
    category: str
    allowed_workers: list[str]
    required_workers: list[str]
    max_workers: int
    rationale: str


class SelectionRationale(BaseModel):
    task_summary: str = Field(min_length=1)
    task_domains: list[str] = Field(default_factory=list)
    selected_workers: list[str] = Field(default_factory=list)
    why_selected: dict[str, str] = Field(default_factory=dict)
    why_not_selected: dict[str, str] = Field(default_factory=dict)


def _contains_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _normalize_question(text: str) -> str:
    return ' '.join(str(text or '').strip().lower().split())


def _has_cjk(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _clean_inline(text: str | None, limit: int = 120) -> str:
    cleaned = ' '.join(str(text or '').split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + '...'


def _build_routing_policy(user_question: str) -> RoutingPolicy:
    raw_text = str(user_question or '')
    text = _normalize_question(raw_text)
    stripped = text.replace(' ', '')
    has_cjk = _has_cjk(raw_text)

    is_greeting = text in ASCII_GREETING_MARKERS or stripped in ASCII_GREETING_MARKERS
    if has_cjk and _contains_any_pattern(raw_text, CJK_GREETING_PATTERNS):
        is_greeting = True
    if is_greeting:
        return RoutingPolicy('direct_answer', [], [], 0, 'Greeting or tiny direct-answer request.')
    worker_ids = [dept.id for dept in get_department_configs() if dept.id != 'crt']
    return RoutingPolicy('orc_selected', worker_ids, [], len(worker_ids), 'Orc must choose the smallest useful worker set from the dynamic roster.')


def _normalize_skill_packs(requested: list[str], available: list[str]) -> list[str]:
    normalized, available_set = [], set(available)
    for item in requested:
        key = str(item).strip()
        if not key:
            continue
        mapped = _SKILL_PACK_ALIASES.get(key, key)
        if mapped in available_set and mapped not in normalized:
            normalized.append(mapped)
    return normalized


def _validate_and_normalize_plan(tasks: dict, workers: dict[str, object]) -> dict[str, WorkerTaskPacket]:
    if not isinstance(tasks, dict):
        raise ValueError('chairman_plan must be a JSON object like {worker_id: task_packet}.')
    if not tasks:
        raise ValueError('chairman_plan must contain at least one selected worker.')
    unexpected = sorted(set(tasks) - set(workers))
    if unexpected:
        raise ValueError(f"Invalid worker IDs in chairman_plan: {', '.join(unexpected)}. Valid worker IDs are: {', '.join(sorted(workers))}.")

    normalized, errors = {}, []
    for dept_id, packet in tasks.items():
        if not isinstance(packet, dict):
            errors.append(f'{dept_id}: task packet must be a JSON object.')
            continue
        try:
            validated = WorkerTaskPacket.model_validate(packet)
            worker = workers[dept_id]
            requested_skill_packs = _normalize_skill_packs(validated.requested_skill_packs, worker.skill_packs)
            validated = validated.model_copy(update={'requested_skill_packs': requested_skill_packs})
            normalized[dept_id] = validated
        except Exception as exc:
            errors.append(f'{dept_id}: invalid task packet ({exc})')
    if errors:
        raise ValueError(' ; '.join(errors))
    return normalized


def _coerce_jsonish(value: Any, *, label: str, fallback: Any = None) -> Any:
    if value is None:
        if fallback is not None:
            return fallback
        raise ValueError(f'{label} is required.')
    if isinstance(value, str):
        text = value.strip()
        if not text and fallback is not None:
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f'{label} is not valid JSON: {exc}') from exc
    return value


def _validate_selection_rationale(raw: Any, *, selected_ids: list[str], workers: dict[str, object]) -> SelectionRationale:
    if not isinstance(raw, dict):
        raise ValueError('selection_rationale must be an object.')
    try:
        payload = SelectionRationale.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f'selection_rationale is invalid: {exc.errors()}') from exc

    normalized_selected = _ordered_unique([str(worker_id).strip() for worker_id in payload.selected_workers])
    expected = _ordered_unique(selected_ids)
    if normalized_selected != expected:
        raise ValueError(f'selection_rationale.selected_workers must exactly match chairman_plan keys: expected {expected}, got {normalized_selected}.')
    if not payload.task_domains:
        raise ValueError('selection_rationale.task_domains must contain at least one free-text domain label chosen by orc.')
    missing_why = [worker_id for worker_id in expected if not str(payload.why_selected.get(worker_id, '')).strip()]
    if missing_why:
        raise ValueError(f'selection_rationale.why_selected must explain every selected worker: missing {missing_why}.')
    unknown_why = sorted(set(payload.why_selected) - set(workers))
    if unknown_why:
        raise ValueError(f'selection_rationale.why_selected references unknown workers: {unknown_why}.')
    return payload.model_copy(update={'selected_workers': expected})


def _selection_rationale_from_plan(
    raw: Any,
    *,
    selected_ids: list[str],
    tasks: dict[str, WorkerTaskPacket],
    workers: dict[str, object],
) -> tuple[SelectionRationale, list[str]]:
    repair_notes: list[str] = []
    raw_payload = raw

    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                raw_payload = json.loads(text)
            except json.JSONDecodeError as exc:
                repair_notes.append(f'repaired malformed selection_rationale JSON: {exc}')
                raw_payload = {
                    'task_summary': _clean_inline(text, limit=220),
                    'task_domains': ['orc_selected'],
                    'selected_workers': selected_ids,
                    'why_selected': {},
                }

    if not isinstance(raw_payload, dict):
        repair_notes.append('rebuilt selection_rationale: payload was not an object')
        raw_payload = {}

    raw_domains = raw_payload.get('task_domains')
    task_domains = [str(item).strip() for item in raw_domains if str(item).strip()] if isinstance(raw_domains, list) else []
    if not task_domains:
        task_domains = ['orc_selected']

    why_selected = raw_payload.get('why_selected') if isinstance(raw_payload.get('why_selected'), dict) else {}
    why_selected = {str(k): str(v).strip() for k, v in why_selected.items() if str(v).strip()}
    why_not_selected = raw_payload.get('why_not_selected') if isinstance(raw_payload.get('why_not_selected'), dict) else {}
    why_not_selected = {str(k): str(v).strip() for k, v in why_not_selected.items() if str(v).strip()}
    for worker_id in selected_ids:
        if worker_id in why_selected:
            continue
        packet = tasks.get(worker_id)
        worker = workers.get(worker_id)
        worker_name = (worker.display_name or worker.name) if worker else worker_id
        reason = packet.objective or packet.task if packet else ''
        why_selected[worker_id] = _clean_inline(f'{worker_name}: {reason}', limit=220)

    candidate = {
        **raw_payload,
        'task_summary': str(raw_payload.get('task_summary') or 'Orc selected workers from chairman_plan.').strip(),
        'task_domains': task_domains,
        'selected_workers': selected_ids,
        'why_selected': why_selected,
        'why_not_selected': why_not_selected,
    }

    try:
        return _validate_selection_rationale(candidate, selected_ids=selected_ids, workers=workers), repair_notes
    except Exception as exc:
        repair_notes.append(f'rebuilt selection_rationale after validation failure: {exc}')
        fallback = {
            'task_summary': 'Orc selected workers from chairman_plan.',
            'task_domains': task_domains,
            'selected_workers': selected_ids,
            'why_selected': why_selected,
            'why_not_selected': {},
        }
        return _validate_selection_rationale(fallback, selected_ids=selected_ids, workers=workers), repair_notes


def _ordered_unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _serialize_result(result, phase: str, packet: WorkerTaskPacket | None, available_skill_packs: list[str] | None = None) -> dict:
    return {'id': result.id, 'name': result.name, 'display_name': result.display_name, 'phase': phase, 'task_packet': packet.model_dump() if packet else None, 'available_skill_packs': available_skill_packs or [], 'status': result.status, 'content': result.content, 'error': result.error, 'startedAt': result.started_at.isoformat() if result.started_at else None, 'completedAt': result.completed_at.isoformat() if result.completed_at else None}


def _build_transfer_record(result, packet: WorkerTaskPacket | None, worker_map: dict[str, object]) -> dict[str, Any]:
    worker = worker_map.get(result.id)
    content = str(result.content or '')
    return {
        'worker_id': result.id,
        'worker_name': (worker.display_name or worker.name) if worker else result.display_name,
        'status': result.status,
        'task_objective': packet.objective if packet else '',
        'required_output': packet.required_output[:5] if packet else [],
        'key_output_preview': _clean_inline(content, limit=1800),
        'error': result.error,
    }


def _build_selected_worker_title(selected_ids: list[str], worker_map: dict[str, object]) -> str:
    names = [worker_map[worker_id].display_name or worker_map[worker_id].name for worker_id in selected_ids]
    if not names:
        return '\u4e3b\u5e2d\u56e2\u51b3\u5b9a\u76f4\u63a5\u56de\u7b54\uff0c\u65e0\u9700\u8c03\u7528\u90e8\u95e8'
    if len(names) == 1:
        return f"\u4e3b\u5e2d\u56e2\u8ba4\u4e3a\u53ef\u4ee5\u8c03\u7528{names[0]}\u8fdb\u884c\u5206\u6790"
    joined_names = '\u3001'.join(names)
    return f"\u4e3b\u5e2d\u56e2\u8ba4\u4e3a\u53ef\u4ee5\u8c03\u7528{joined_names}\u8fdb\u884c\u5206\u6790"


def _build_selected_worker_summary(tasks: dict[str, WorkerTaskPacket], routing_policy: RoutingPolicy) -> str:
    worker_summaries = [f'{worker_id}: {_clean_inline(packet.task or packet.objective, limit=48)}' for worker_id, packet in tasks.items()]
    return _clean_inline(f"{routing_policy.rationale} | {'; '.join(worker_summaries)}", limit=150)


def _build_worker_output_sections(worker_results, tasks: dict[str, WorkerTaskPacket], worker_map: dict[str, object]) -> tuple[list[str], list[dict]]:
    worker_output_parts: list[str] = []
    department_results: list[dict] = []
    for result in worker_results:
        packet = tasks.get(result.id)
        available_skill_packs = list(worker_map[result.id].skill_packs)
        department_results.append(_serialize_result(result, phase='worker', packet=packet, available_skill_packs=available_skill_packs))
        header = f"## {result.name} ({result.display_name})"
        transfer_record = _build_transfer_record(result, packet, worker_map)
        worker_output_parts.append(f"{header}\n<structured_worker_transfer>\n{json.dumps(transfer_record, ensure_ascii=False, indent=2)}\n</structured_worker_transfer>")
    return worker_output_parts, department_results


def _build_critic_task(*, user_question: str, routing_policy: RoutingPolicy, selected_ids: list[str], tasks: dict[str, WorkerTaskPacket], worker_map: dict[str, object], worker_summary: str, review_round: int = 1) -> str:
    round_label = 'initial review' if review_round == 1 else f'review round {review_round}'
    return (
        'Review the worker results as the single validation authority for this run.\n\n'
        f"[Review round]\n{round_label}\n\n"
        f"[User question]\n{user_question}\n\n"
        f"[Routing category]\n{routing_policy.category}\n\n"
        f"[Routing rationale]\n{routing_policy.rationale}\n\n"
        f"[Selected workers]\n{', '.join(selected_ids)}\n\n"
        f"[Chairman task packets]\n{json.dumps({dept_id: packet.model_dump() for dept_id, packet in tasks.items()}, ensure_ascii=False, indent=2)}\n\n"
        f"[Worker registered skill packs]\n{json.dumps({dept_id: worker_map[dept_id].skill_packs for dept_id in selected_ids}, ensure_ascii=False, indent=2)}\n\n"
        f"[Worker outputs]\n{worker_summary}\n\n"
        'Validate not only the text conclusions but also any referenced artifacts or deliverables. '
        'Focus on conflict, omission, execution risk, delivery quality, and whether the result can be shipped to the user. '
        'You must end with a <validation_report> block using pass_gate, summary, and rework_targets.'
    )




def _build_rework_packet(worker_id: str, packet: WorkerTaskPacket, feedback: str) -> WorkerTaskPacket:
    revised_task = (
        f"Revise the previous output for {worker_id}. Original task: {packet.task}\n\n"
        f"Critic-required fixes:\n- {feedback}\n\n"
        'Return an updated result that directly addresses the critic feedback.'
    )
    revised_notes = [*packet.notes, f'Critic feedback: {feedback}']
    revised_success = [*packet.success_criteria, f'Explicitly resolve critic feedback: {feedback}']
    return packet.model_copy(update={
        'task': revised_task,
        'notes': revised_notes,
        'success_criteria': revised_success,
        'priority': 'high',
    })


@tool(response_format='content_and_artifact')
async def delegate_to_departments(
    user_question: Annotated[str, 'The original user question/request retained for critic review and lead-agent traceability.'],
    selection_rationale: Annotated[dict[str, Any] | str, 'Orc-authored selection rationale. Free-text task_domains; selected_workers must match chairman_plan keys.'],
    chairman_plan: Annotated[dict[str, Any] | str, 'Object mapping selected worker department IDs to structured task packets. Do NOT include crt.'],
    checklist_draft: Annotated[list[dict[str, Any]] | dict[str, Any] | str, 'Checklist drafted by orc. Each item must include item_id, title, owner, depends_on.'],
    checklist_self_check: Annotated[dict[str, Any] | str, 'Self-check object with passed, issues, fixes, and selected_workers.'],
) -> tuple[str, dict]:
    """Delegate selected worker departments and run critic review."""
    raw_tasks = _coerce_jsonish(chairman_plan, label='chairman_plan')
    raw_checklist = _coerce_jsonish(checklist_draft, label='checklist_draft', fallback=[])
    raw_self_check = _coerce_jsonish(checklist_self_check, label='checklist_self_check', fallback={})

    all_depts = get_department_configs()
    worker_map = {dept.id: dept for dept in all_depts if dept.id != 'crt'}
    critic_dept = next((dept for dept in all_depts if dept.id == 'crt'), None)
    tasks = _validate_and_normalize_plan(raw_tasks, worker_map)
    selected_ids = [dept_id for dept_id in worker_map if dept_id in tasks]
    validated_selection, selection_repair_notes = _selection_rationale_from_plan(
        selection_rationale,
        selected_ids=selected_ids,
        tasks=tasks,
        workers=worker_map,
    )
    routing_policy = RoutingPolicy(
        category='orc_selected',
        allowed_workers=list(worker_map),
        required_workers=[],
        max_workers=len(worker_map),
        rationale=f"Orc selected workers for domains: {', '.join(validated_selection.task_domains)}",
    )
    routing_alignment_changes: list[str] = [*selection_repair_notes]
    try:
        validated_checklist = validate_checklist_draft(raw_checklist, route=routing_policy.category, selected_workers=selected_ids)
    except Exception as exc:
        routing_alignment_changes.append(f'rebuilt checklist: {exc}')
        validated_checklist = build_initial_checklist(current_session_id() or 'adhoc', user_question, routing_policy.category, selected_ids)
    try:
        validated_self_check = validate_checklist_self_check(raw_self_check, selected_workers=selected_ids)
    except Exception as exc:
        routing_alignment_changes.append(f'rebuilt checklist self-check: {exc}')
        validated_self_check = validate_checklist_self_check({
            'passed': True,
            'issues': [],
            'fixes': routing_alignment_changes,
            'selected_workers': selected_ids,
        }, selected_workers=selected_ids)
    session_id = current_session_id()

    if session_id:
        state = sync_session_checklist(
            session_id,
            validated_checklist,
            user_goal=user_question,
            task_type=routing_policy.category,
            selected_workers=selected_ids,
            run_status='running',
        )
        state = update_checklist_item(
            session_id,
            validated_checklist[0].item_id,
            status='done',
            result_preview=_build_selected_worker_summary(tasks, routing_policy),
            verification_status='checklist_validated',
        )
        await emit_checklist_sync(state)

    checklist_validation_summary = '清单结构和部门选择已通过校验，可以开始分发执行。'
    if not validated_self_check.passed:
        warning = '; '.join(validated_self_check.issues or []) or '自校验未通过，已按规范结果继续执行。'
        fixes = '; '.join(validated_self_check.fixes or [])
        checklist_validation_summary = f'清单结构已通过硬校验，自校验提示：{warning}' + (f'。建议修正：{fixes}' if fixes else '')

    await emit_run_step(
        step_id='orc_checklist_validation',
        phase='orc',
        agent_id='orc',
        status='completed',
        title='执行清单已完成校验',
        summary=_clean_inline(checklist_validation_summary, limit=110),
        meta={'selected_workers': selected_ids, 'route': routing_policy.category, 'selection_rationale': validated_selection.model_dump(), 'checklist_items': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump()},
    )
    await emit_run_step(step_id='orc_selected_workers', phase='orc', agent_id='orc', status='completed', title=_build_selected_worker_title(selected_ids, worker_map), summary=_build_selected_worker_summary(tasks, routing_policy), meta={'selected_workers': selected_ids, 'route': routing_policy.category, 'selection_rationale': validated_selection.model_dump(), 'checklist_items': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump()})
    logger.info('Phase 1: Running selected worker departments: %s | route=%s', selected_ids, routing_policy.category)
    worker_results = await run_departments(department_ids=selected_ids, tasks=tasks)

    worker_output_parts, department_results = _build_worker_output_sections(worker_results, tasks, worker_map)
    worker_summary = '\n\n---\n\n'.join(worker_output_parts) if worker_output_parts else '(No worker output)'
    validation_report = None

    if critic_dept:
        logger.info('Phase 2: Critic (crt) reviewing results | route=%s', routing_policy.category)
        await emit_run_step(
            step_id='critic_review_phase_1',
            phase='critic',
            agent_id='crt',
            status='running',
            title='质检部开始统一验证',
            summary='正在审查各部门输出之间的冲突、遗漏、风险和交付可用性。',
            meta={'review_round': 1, 'selected_workers': selected_ids},
        )
        if session_id:
            state = update_checklist_item(
                session_id,
                'critic_review',
                status='running',
                result_preview='Reviewing cross-department conflicts, quality risks, and delivery readiness.',
            )
            await emit_checklist_sync(state)

        critic_result = await run_single_department(
            dept_id='crt',
            task=_build_critic_task(
                user_question=user_question,
                routing_policy=routing_policy,
                selected_ids=selected_ids,
                tasks=tasks,
                worker_map=worker_map,
                worker_summary=worker_summary,
                review_round=1,
            ),
            step_suffix='review1',
        )
        department_results.append(_serialize_result(critic_result, phase='critic', packet=None))
        validation_report = parse_validation_report(critic_result.content or critic_result.error, status=critic_result.status)
        await emit_run_step(
            step_id='critic_review_phase_1',
            phase='critic',
            agent_id='crt',
            status='completed' if critic_result.status == 'completed' else 'failed',
            title='质检部完成首轮验证',
            summary=_clean_inline(validation_report.summary or critic_result.content or critic_result.error or critic_result.status, limit=120),
            meta={'review_round': 1, 'pass_gate': validation_report.pass_gate},
        )
        if session_id:
            state = set_validation_report(session_id, validation_report)
            state = update_checklist_item(
                session_id,
                'critic_review',
                status='done' if critic_result.status == 'completed' else 'failed',
                result_preview=validation_report.summary or critic_result.content or critic_result.error or critic_result.status,
                result_ref='crt',
                verification_status=validation_report.pass_gate,
            )
            state = append_artifact(
                session_id,
                owner='crt',
                kind='validation_report',
                content=validation_report.raw_text or (critic_result.content or critic_result.error or ''),
                linked_checklist_item='critic_review',
            )
            for finding in validation_report.rework_targets:
                if finding.owner in worker_map:
                    state = upsert_worker_shard(
                        session_id,
                        finding.owner,
                        validation_feedback=finding.summary,
                        status='needs_rework' if validation_report.pass_gate != 'passed' else 'validated',
                    )
            await emit_checklist_sync(state)

        if validation_report.pass_gate == 'fixes_required' and validation_report.rework_targets:
            rework_pairs = [(finding.owner, finding.summary) for finding in validation_report.rework_targets if finding.owner in tasks]
            if rework_pairs:
                await emit_run_step(
                    step_id='orc_rework_dispatch',
                    phase='orc',
                    agent_id='orc',
                    status='running',
                    title='主席团开始安排返工',
                    summary=_clean_inline('; '.join(f'{owner}: {feedback}' for owner, feedback in rework_pairs), limit=120),
                    meta={'rework_targets': [owner for owner, _ in rework_pairs]},
                )
                for owner, feedback in rework_pairs:
                    tasks[owner] = _build_rework_packet(owner, tasks[owner], feedback)
                    if session_id:
                        state = upsert_worker_shard(session_id, owner, task_packet=tasks[owner].model_dump(), validation_feedback=feedback, increment_retry=True, status='reworking')
                        await emit_checklist_sync(state)
                rework_results = await asyncio.gather(*[
                        run_single_department(
                            dept_id=owner,
                            task=tasks[owner].task,
                            task_packet=tasks[owner],
                            step_suffix=f'rework{index}',
                        )
                        for index, (owner, _feedback) in enumerate(rework_pairs, start=1)
                    ])
                await emit_run_step(
                    step_id='orc_rework_dispatch',
                    phase='orc',
                    agent_id='orc',
                    status='completed',
                    title='主席团已下发返工任务',
                    summary='被点名的部门正在根据质检意见修正结果。',
                    meta={'rework_targets': [owner for owner, _ in rework_pairs]},
                )
                rework_output_parts, rework_department_results = _build_worker_output_sections(rework_results, tasks, worker_map)
                department_results.extend(rework_department_results)
                merged_sections = [section for section in worker_output_parts if all(not section.startswith(f'## {worker_map[owner].name} ({worker_map[owner].display_name or owner})') for owner, _ in rework_pairs)]
                merged_sections.extend(rework_output_parts)
                worker_summary = '\n\n---\n\n'.join(merged_sections) if merged_sections else worker_summary

                await emit_run_step(
                    step_id='critic_review_phase_2',
                    phase='critic',
                    agent_id='crt',
                    status='running',
                    title='质检部正在复审返工结果',
                    summary='正在检查返工后的结果是否已经达到可交付标准。',
                    meta={'review_round': 2, 'rework_targets': [owner for owner, _ in rework_pairs]},
                )
                critic_result = await run_single_department(
                    dept_id='crt',
                    task=_build_critic_task(
                        user_question=user_question,
                        routing_policy=routing_policy,
                        selected_ids=selected_ids,
                        tasks=tasks,
                        worker_map=worker_map,
                        worker_summary=worker_summary,
                        review_round=2,
                    ),
                    step_suffix='review2',
                )
                department_results.append(_serialize_result(critic_result, phase='critic', packet=None))
                validation_report = parse_validation_report(critic_result.content or critic_result.error, status=critic_result.status)
                await emit_run_step(
                    step_id='critic_review_phase_2',
                    phase='critic',
                    agent_id='crt',
                    status='completed' if critic_result.status == 'completed' else 'failed',
                    title='质检部完成复审',
                    summary=_clean_inline(validation_report.summary or critic_result.content or critic_result.error or critic_result.status, limit=120),
                    meta={'review_round': 2, 'pass_gate': validation_report.pass_gate},
                )
                if session_id:
                    state = set_validation_report(session_id, validation_report)
                    state = update_checklist_item(
                        session_id,
                        'critic_review',
                        status='done' if critic_result.status == 'completed' else 'failed',
                        result_preview=validation_report.summary or critic_result.content or critic_result.error or critic_result.status,
                        result_ref='crt',
                        verification_status=validation_report.pass_gate,
                    )
                    state = append_artifact(
                        session_id,
                        owner='crt',
                        kind='validation_report_recheck',
                        content=validation_report.raw_text or (critic_result.content or critic_result.error or ''),
                        linked_checklist_item='critic_review',
                    )
                    for owner, feedback in rework_pairs:
                        state = upsert_worker_shard(session_id, owner, validation_feedback=feedback, status='validated' if validation_report.pass_gate == 'passed' else 'needs_rework')
                    await emit_checklist_sync(state)

        critic_header = f"## {critic_result.name} ({critic_result.display_name}) - Validation Review"
        critic_section = f"{critic_header}\n{critic_result.content}" if critic_result.status == 'completed' else f"{critic_header}\nReview failed: {critic_result.error or critic_result.status}"
        content = f"{worker_summary}\n\n{'=' * 40}\n\n{critic_section}"
    else:
        logger.warning('No critic department (crt) found, skipping review phase')
        content = worker_summary

    if session_id:
        state = update_checklist_item(
            session_id,
            'orc_final',
            status='running',
            result_preview='Assembling the final answer for the user.',
        )
        await emit_checklist_sync(state)

    await emit_run_step(step_id='orc_finalizing', phase='final', agent_id='orc', status='running', title='主席团正在整合验证结论并生成最终答复', summary='正在吸收各部门结论和质检意见，整理给用户的最终结果。', meta={'selected_workers': selected_ids, 'validation_gate': validation_report.pass_gate if validation_report else 'unknown'})
    artifact = {'user_question': user_question, 'routing_policy': asdict(routing_policy), 'selection_rationale': validated_selection.model_dump(), 'chairman_plan': {dept_id: packet.model_dump() for dept_id, packet in tasks.items()}, 'checklist_draft': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump(), 'validation_report': validation_report.model_dump() if validation_report else None, 'selected_workers': selected_ids, 'department_results': department_results}
    return content, artifact
