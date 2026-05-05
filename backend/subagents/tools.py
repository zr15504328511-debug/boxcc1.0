"""Department delegation tool for the lead agent.

Flow: Chairman (orc) selects workers -> Worker departments run in parallel -> Critic (crt) reviews.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Annotated

from langchain_core.tools import tool

from runtime_events import current_session_id, emit_run_step
from session.checklist import append_artifact, emit_checklist_sync, parse_validation_report, set_validation_report, sync_session_checklist, update_checklist_item, upsert_worker_shard, validate_checklist_draft, validate_checklist_self_check
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
ASCII_QUALITY_MARKERS = {'fabric', 'material', 'fit', 'wear', 'complaint', 'complaints', 'return', 'returns', 'refund', 'defect', 'defects', 'shrink', 'wrinkle', 'pilling', 'transparency', 'colorfastness', 'quality risk', 'quality issue', 'construction risk', 'seam issue'}
ASCII_PLANNING_MARKERS = {'planning', 'sku', 'launch', 'assortment', 'series', 'wave', 'schedule', 'roadmap', 'calendar', 'merchandising'}
ASCII_FINANCE_MARKERS = {'cost', 'margin', 'profit', 'pricing', 'price', 'budget', 'commercial', 'gm', 'roi', 'markup'}
ASCII_COPY_MARKERS = {'copy', 'selling point', 'selling points', 'slogan', 'campaign', 'product page', 'marketing', 'headline', 'storytelling'}
ASCII_INTEGRATED_MARKERS = {'full proposal', 'full review', 'go/no-go', 'integrated', 'cross-functional', 'complete package', 'all departments'}


def _u(value: str) -> str:
    return value.encode('ascii').decode('unicode_escape')


CJK_GREETING_PATTERNS = [_u(r'\u4f60\u597d'), _u(r'\u60a8\u597d'), _u(r'\u65e9\u4e0a\u597d'), _u(r'\u4e0b\u5348\u597d'), _u(r'\u665a\u4e0a\u597d'), _u(r'\u8c22\u8c22')]
CJK_QUALITY_PATTERNS = [_u(r'\u5ba2\u8bc9'), _u(r'\u9000\u8d27'), _u(r'\u9000\u6b3e'), _u(r'\u98ce\u9669\u70b9'), _u(r'\u9762\u6599'), _u(r'\u6750\u8d28'), _u(r'\u7f0e\u9762'), _u(r'\u919b\u9178'), _u(r'\u7248\u578b'), _u(r'\u4e0a\u8eab'), _u(r'\u7a7f\u7740'), _u(r'\u505a\u5de5'), _u(r'\u5de5\u827a'), _u(r'\u8d77\u76b1'), _u(r'\u52fe\u4e1d'), _u(r'\u900f'), _u(r'\u53d8\u5f62'), _u(r'\u7f29\u6c34'), _u(r'\u7206\u7ebf'), _u(r'\u5f00\u7ebf'), _u(r'\u8d28\u91cf'), _u(r'\u95ee\u9898'), _u(r'\u6bdb\u75c5'), _u(r'\u7ec6\u8282')]
CJK_PLANNING_PATTERNS = [_u(r'\u4f01\u5212'), _u(r'\u89c4\u5212'), _u(r'\u7cfb\u5217'), _u(r'\u6ce2\u6bb5'), _u(r'\u4e0a\u65b0'), _u(r'\u8282\u594f'), _u(r'\u5f00\u53d1\u6392\u671f'), _u(r'\u5f00\u53d1\u8282\u594f'), _u(r'\u5b63\u8282'), _u(r'\u6b3e\u5f0f\u7ed3\u6784'), 'sku']
CJK_FINANCE_PATTERNS = [_u(r'\u6210\u672c'), _u(r'\u5b9a\u4ef7'), _u(r'\u6bdb\u5229'), _u(r'\u5229\u6da6'), _u(r'\u9884\u7b97'), _u(r'\u552e\u4ef7'), _u(r'\u7ecf\u8425'), _u(r'\u6295\u4ea7\u6bd4'), _u(r'\u76c8\u4e8f'), _u(r'\u5229\u6da6\u7387'), _u(r'\u76d8\u8d27')]
CJK_COPY_PATTERNS = [_u(r'\u6587\u6848'), _u(r'\u5356\u70b9'), _u(r'\u5ba3\u4f20'), _u(r'\u63a8\u5e7f'), _u(r'\u8be6\u60c5\u9875'), _u(r'\u6807\u9898'), _u(r'\u8bdd\u672f'), _u(r'\u79cd\u8349')]
CJK_INTEGRATED_PATTERNS = [_u(r'\u5b8c\u6574\u65b9\u6848'), _u(r'\u5168\u6848'), _u(r'\u4f1a\u5ba1'), _u(r'\u8de8\u90e8\u95e8'), _u(r'\u7efc\u5408\u8bc4\u4f30'), _u(r'\u603b\u4f53\u65b9\u6848'), _u(r'\u5168\u90e8\u90e8\u95e8'), _u(r'\u7acb\u9879\u8bc4\u5ba1')]


@dataclass
class RoutingPolicy:
    category: str
    allowed_workers: list[str]
    required_workers: list[str]
    max_workers: int
    rationale: str


def _contains_any(text: str, markers: set[str]) -> bool:
    return any(marker in text for marker in markers)


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

    has_integrated = _contains_any(text, ASCII_INTEGRATED_MARKERS)
    has_quality = _contains_any(text, ASCII_QUALITY_MARKERS)
    has_planning = _contains_any(text, ASCII_PLANNING_MARKERS)
    has_finance = _contains_any(text, ASCII_FINANCE_MARKERS)
    has_copy = _contains_any(text, ASCII_COPY_MARKERS)

    if has_cjk:
        has_integrated = has_integrated or _contains_any_pattern(raw_text, CJK_INTEGRATED_PATTERNS)
        has_quality = has_quality or _contains_any_pattern(raw_text, CJK_QUALITY_PATTERNS)
        has_planning = has_planning or _contains_any_pattern(raw_text, CJK_PLANNING_PATTERNS)
        has_finance = has_finance or _contains_any_pattern(raw_text, CJK_FINANCE_PATTERNS)
        has_copy = has_copy or _contains_any_pattern(raw_text, CJK_COPY_PATTERNS)

    if has_integrated:
        return RoutingPolicy('integrated_review', ['dom', 'pln', 'ana', 'cpy'], [], 4, 'Explicit integrated or full-solution review request.')

    categories, allowed, required = [], [], []

    def add_allowed(*workers: str) -> None:
        for worker in workers:
            if worker not in allowed:
                allowed.append(worker)

    def add_required(*workers: str) -> None:
        for worker in workers:
            if worker not in required:
                required.append(worker)

    if has_quality:
        categories.append('quality_risk'); add_allowed('dom', 'pln'); add_required('dom')
    if has_planning:
        categories.append('planning'); add_allowed('pln', 'dom'); add_required('pln')
    if has_finance:
        categories.append('finance'); add_allowed('ana', 'pln'); add_required('ana')
    if has_copy:
        categories.append('copywriting'); add_allowed('cpy', 'pln'); add_required('cpy')

    if not categories:
        return RoutingPolicy('default_quality_fallback', ['dom', 'pln'], ['dom'], 2, 'Fallback to domain-risk analysis with optional planning support.')
    if len(categories) == 1:
        return RoutingPolicy(categories[0], allowed, required, 2, f'Single routing category: {categories[0]}')
    return RoutingPolicy('mixed', allowed, required, min(3, len(allowed)), f'Mixed routing categories: {", ".join(categories)}')


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


def _enforce_routing_policy(user_question: str, selected_ids: list[str]) -> RoutingPolicy:
    policy = _build_routing_policy(user_question)
    selected = list(selected_ids)
    if policy.category == 'direct_answer':
        raise ValueError('This request looks like a direct-answer request and should not call delegate_to_departments.')
    disallowed = [worker for worker in selected if worker not in policy.allowed_workers]
    if disallowed:
        raise ValueError(f"Routing policy '{policy.category}' does not allow workers: {', '.join(disallowed)}. Allowed workers: {', '.join(policy.allowed_workers)}.")
    missing_required = [worker for worker in policy.required_workers if worker not in selected]
    if missing_required:
        raise ValueError(f"Routing policy '{policy.category}' requires workers: {', '.join(missing_required)}.")
    if len(selected) > policy.max_workers:
        raise ValueError(f"Routing policy '{policy.category}' allows at most {policy.max_workers} workers, got {len(selected)}.")
    return policy


def _serialize_result(result, phase: str, packet: WorkerTaskPacket | None, available_skill_packs: list[str] | None = None) -> dict:
    return {'id': result.id, 'name': result.name, 'display_name': result.display_name, 'phase': phase, 'task_packet': packet.model_dump() if packet else None, 'available_skill_packs': available_skill_packs or [], 'status': result.status, 'content': result.content, 'error': result.error, 'startedAt': result.started_at.isoformat() if result.started_at else None, 'completedAt': result.completed_at.isoformat() if result.completed_at else None}


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
        if result.status == 'completed':
            worker_output_parts.append(f"{header}\n{result.content}")
        elif result.status == 'timed_out':
            worker_output_parts.append(f"{header}\nTimed out: {result.error}")
        elif result.status == 'failed':
            worker_output_parts.append(f"{header}\nFailed: {result.error}")
        else:
            worker_output_parts.append(f"{header}\nStatus: {result.status}")
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
    chairman_plan: Annotated[str, 'JSON object mapping only the selected worker department IDs to structured task packets. Do NOT include crt.'],
    checklist_draft: Annotated[str, 'JSON checklist drafted by orc. Each item must include item_id, title, owner, depends_on.'],
    checklist_self_check: Annotated[str, 'JSON self-check object with passed, issues, fixes, and selected_workers.'],
) -> tuple[str, dict]:
    """Delegate selected worker departments and run critic review."""
    try:
        raw_tasks = json.loads(chairman_plan)
    except json.JSONDecodeError as exc:
        raise ValueError(f'chairman_plan is not valid JSON: {exc}') from exc

    try:
        raw_checklist = json.loads(checklist_draft)
    except json.JSONDecodeError as exc:
        raise ValueError(f'checklist_draft is not valid JSON: {exc}') from exc

    try:
        raw_self_check = json.loads(checklist_self_check)
    except json.JSONDecodeError as exc:
        raise ValueError(f'checklist_self_check is not valid JSON: {exc}') from exc

    all_depts = get_department_configs()
    worker_map = {dept.id: dept for dept in all_depts if dept.id != 'crt'}
    critic_dept = next((dept for dept in all_depts if dept.id == 'crt'), None)
    tasks = _validate_and_normalize_plan(raw_tasks, worker_map)
    selected_ids = [dept_id for dept_id in worker_map if dept_id in tasks]
    routing_policy = _enforce_routing_policy(user_question, selected_ids)
    validated_checklist = validate_checklist_draft(raw_checklist, route=routing_policy.category, selected_workers=selected_ids)
    validated_self_check = validate_checklist_self_check(raw_self_check, selected_workers=selected_ids)
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
        meta={'selected_workers': selected_ids, 'checklist_items': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump()},
    )
    await emit_run_step(step_id='orc_selected_workers', phase='orc', agent_id='orc', status='completed', title=_build_selected_worker_title(selected_ids, worker_map), summary=_build_selected_worker_summary(tasks, routing_policy), meta={'selected_workers': selected_ids, 'route': routing_policy.category, 'checklist_items': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump()})
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
                rework_results = []
                for index, (owner, feedback) in enumerate(rework_pairs, start=1):
                    rework_results.append(
                        await run_single_department(
                            dept_id=owner,
                            task=tasks[owner].task,
                            task_packet=tasks[owner],
                            step_suffix=f'rework{index}',
                        )
                    )
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
    artifact = {'user_question': user_question, 'routing_policy': asdict(routing_policy), 'chairman_plan': {dept_id: packet.model_dump() for dept_id, packet in tasks.items()}, 'checklist_draft': [item.model_dump() for item in validated_checklist], 'checklist_self_check': validated_self_check.model_dump(), 'validation_report': validation_report.model_dump() if validation_report else None, 'selected_workers': selected_ids, 'department_results': department_results}
    return content, artifact
