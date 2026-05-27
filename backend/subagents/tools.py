"""Agent delegation tool for the lead agent.

Flow: Chairman (orc) reads the agent catalog → selects specialist agents →
fan out in parallel → critic (`crt`) reviews → optional rework loop.

The orchestration **execution** lives in `subagents/workflow.py` as a
LangGraph StateGraph. This module is now a thin wrapper:

  1. Validate the JSON inputs (chairman_plan, checklist, self_check)
  2. Enforce routing policy (greeting / integrated / open + hard rules)
  3. Sync the session state & emit the "ready to dispatch" events
  4. Hand off to `run_delegate_workflow`
  5. Return `(content, artifact)` for LangChain

The routing in `_build_routing_policy` is intentionally **slim**: just
greeting/integrated detection + a handful of HARD_RULES (must-include
for risky topics). Everything else lands in `open` and lets orc pick
from the agent catalog using its own LLM judgment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Annotated

from langchain_core.tools import tool

from runtime_events import current_message_id, current_session_id, current_turn_id, emit_run_step
from session.checklist import (
    emit_checklist_sync,
    sync_session_checklist,
    update_checklist_item,
    validate_checklist_draft,
    validate_checklist_self_check,
)
from subagents.registry import get_agent_configs
from subagents.task_packet import WorkerTaskPacket
from subagents.workflow import run_delegate_workflow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slim routing — orc reads the catalog and makes its own selection; this
# policy only enforces:
#   1. greetings → direct answer (no delegate)
#   2. "完整方案 / 全方案 / integrated" → all enabled workers allowed
#   3. a handful of HARD_RULES (must-include for risky topics)
#   4. everything else → `open` (all workers allowed, cap 6)
# ---------------------------------------------------------------------------

ASCII_GREETING_MARKERS = {
    'hello', 'hi', 'hey', 'thanks', 'thank you',
    'good morning', 'good evening', 'good night',
}
CJK_GREETING_PATTERNS = [
    '你好', '您好', '早上好', '下午好', '晚上好', '谢谢', '感谢', '在吗',
]

ASCII_INTEGRATED_MARKERS = {
    'full proposal', 'full review', 'go/no-go', 'integrated',
    'cross-functional', 'complete package', 'all departments', 'end-to-end',
    'all agents',
}
CJK_INTEGRATED_PATTERNS = [
    '完整方案', '全方案', '会审', '跨部门', '综合评估', '总体方案',
    '全部部门', '立项评审', '一站到底', '全案',
]

# (needles, must-include agent ids, rationale). Matching is case-insensitive
# on ASCII; CJK needles match raw text.
HARD_RULES: list[tuple[tuple[str, ...], list[str], str]] = [
    (
        ('合同', 'contract'),
        ['biz_legal'],
        '合同 / Contract — 必须法务把关',
    ),
    (
        ('召回', 'recall', '12315', '集体投诉', '维权', '消协', 'class action', 'lawsuit'),
        ['biz_legal', 'biz_voc'],
        '重大客诉 / 维权 / 召回 — 必须法务 + 客服',
    ),
    (
        ('广告法', '禁用词', '绝对化', 'ad law'),
        ['biz_legal', 'gro_content'],
        '广告法风险 — 必须法务 + 内容审核',
    ),
    (
        ('退货率', '退换', '退货原因', 'return rate'),
        ['biz_voc', 'mer_ops'],
        '退货率分析 — 必须客服 + 商品运营',
    ),
    (
        ('跌价', '库存减值', 'writedown', 'impairment'),
        ['biz_fin', 'mer_ops'],
        '跌价 / 库存减值 — 必须财务 + 商品运营',
    ),
    (
        ('pipl', '个保法', '数据安全', '隐私', '权限审计'),
        ['biz_legal', 'biz_it'],
        '数据 / 隐私 / 个保法 — 必须法务 + IT',
    ),
]


@dataclass
class RoutingPolicy:
    """Result of routing classification.

    Keep this shape stable — the four fields are serialized into the
    `delegate_to_departments` artifact JSON that the frontend reads.
    """

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
    return bool(re.search(r'[一-鿿]', text))


def _clean_inline(text: str | None, limit: int = 120) -> str:
    cleaned = ' '.join(str(text or '').split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + '...'


def _enabled_worker_ids() -> list[str]:
    """All enabled worker agent ids (excludes critic)."""
    return [a.id for a in get_agent_configs() if a.id != 'crt']


def _build_routing_policy(user_question: str) -> RoutingPolicy:
    """Classify the user question; return a routing policy."""
    raw_text = str(user_question or '')
    text = _normalize_question(raw_text)
    stripped = text.replace(' ', '')

    is_greeting = (
        text in ASCII_GREETING_MARKERS
        or stripped in ASCII_GREETING_MARKERS
        or _contains_any_pattern(raw_text, CJK_GREETING_PATTERNS)
    )
    if is_greeting:
        return RoutingPolicy('direct_answer', [], [], 0, 'Greeting or tiny direct-answer request.')

    workers = _enabled_worker_ids()

    if _contains_any(text, ASCII_INTEGRATED_MARKERS) or _contains_any_pattern(raw_text, CJK_INTEGRATED_PATTERNS):
        return RoutingPolicy(
            'integrated_review',
            workers,
            [],
            len(workers),
            'Explicit integrated / cross-functional / 完整方案 request.',
        )

    required: list[str] = []
    rationale_bits: list[str] = []
    for needles, req_agents, why in HARD_RULES:
        if any(n.lower() in text or n in raw_text for n in needles):
            for w in req_agents:
                if w not in required and w in workers:
                    required.append(w)
            rationale_bits.append(why)

    return RoutingPolicy(
        'open',
        workers,
        required,
        min(6, len(workers)),
        '; '.join(rationale_bits) if rationale_bits else 'Open routing — orc selects from catalog.',
    )


def _validate_and_normalize_plan(tasks: dict, workers: dict[str, object]) -> dict[str, WorkerTaskPacket]:
    """Validate orc's `chairman_plan` and produce normalized task packets."""
    if not isinstance(tasks, dict):
        raise ValueError('chairman_plan must be a JSON object like {agent_id: task_packet}.')
    if not tasks:
        raise ValueError('chairman_plan must contain at least one selected agent.')
    unexpected = sorted(set(tasks) - set(workers))
    if unexpected:
        raise ValueError(
            f"Invalid agent IDs in chairman_plan: {', '.join(unexpected)}. "
            f"Valid agent IDs are: {', '.join(sorted(workers))}."
        )

    normalized, errors = {}, []
    for agent_id, packet in tasks.items():
        if not isinstance(packet, dict):
            errors.append(f'{agent_id}: task packet must be a JSON object.')
            continue
        try:
            validated = WorkerTaskPacket.model_validate(packet)
            normalized[agent_id] = validated
        except Exception as exc:
            errors.append(f'{agent_id}: invalid task packet ({exc})')
    if errors:
        raise ValueError(' ; '.join(errors))
    return normalized


def _enforce_routing_policy(user_question: str, selected_ids: list[str]) -> RoutingPolicy:
    policy = _build_routing_policy(user_question)
    selected = list(selected_ids)
    if policy.category == 'direct_answer':
        raise ValueError('This request looks like a direct-answer request and should not call delegate_to_departments.')
    disallowed = [w for w in selected if w not in policy.allowed_workers]
    if disallowed:
        raise ValueError(
            f"Routing policy '{policy.category}' does not allow agents: {', '.join(disallowed)}. "
            f"Allowed agents: {', '.join(policy.allowed_workers)}."
        )
    missing_required = [w for w in policy.required_workers if w not in selected]
    if missing_required:
        raise ValueError(
            f"Routing policy '{policy.category}' requires agents: {', '.join(missing_required)}."
        )
    if len(selected) > policy.max_workers:
        raise ValueError(
            f"Routing policy '{policy.category}' allows at most {policy.max_workers} agents, got {len(selected)}."
        )
    return policy


def _build_selected_worker_title(selected_ids: list[str], worker_map: dict[str, object]) -> str:
    names = [worker_map[w].name for w in selected_ids if w in worker_map]
    if not names:
        return '主席团决定直接回答，无需调用 agent'
    if len(names) == 1:
        return f"主席团认为可以调用 {names[0]} 进行分析"
    return f"主席团认为可以调用 {' / '.join(names)} 进行分析"


def _build_selected_worker_summary(tasks: dict[str, WorkerTaskPacket], routing_policy: RoutingPolicy) -> str:
    summaries = [f'{aid}: {_clean_inline(p.task or p.objective, limit=48)}' for aid, p in tasks.items()]
    return _clean_inline(f"{routing_policy.rationale} | {'; '.join(summaries)}", limit=150)


@tool(response_format='content_and_artifact')
async def delegate_to_departments(
    user_question: Annotated[str, 'The original user question/request retained for critic review and lead-agent traceability.'],
    chairman_plan: Annotated[str, 'JSON object mapping selected agent IDs to structured task packets. Do NOT include crt — the critic runs automatically in Phase 2.'],
    checklist_draft: Annotated[str, 'JSON checklist drafted by orc. Each item must include item_id, title, owner, depends_on.'],
    checklist_self_check: Annotated[str, 'JSON self-check object with passed, issues, fixes, and selected_workers.'],
    deliverable_type_id: Annotated[str, 'Optional: id of a registered deliverable template (e.g. "management_ppt", "product_detail_page"). If set, critic uses the template\'s quality_gates as review checklist.'] = "",
) -> tuple[str, dict]:
    """Delegate selected specialist agents and run critic review.

    Thin wrapper that:
      1. Parses & validates the three JSON inputs
      2. Resolves the registry + routing policy
      3. Syncs the session checklist + emits pre-dispatch events
      4. Hands off to the LangGraph workflow in `subagents.workflow`
    """
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

    all_agents = get_agent_configs()
    worker_map = {a.id: a for a in all_agents if a.id != 'crt'}
    critic_agent = next((a for a in all_agents if a.id == 'crt'), None)

    tasks = _validate_and_normalize_plan(raw_tasks, worker_map)
    selected_ids = [aid for aid in worker_map if aid in tasks]
    routing_policy = _enforce_routing_policy(user_question, selected_ids)
    validated_checklist = validate_checklist_draft(
        raw_checklist, route=routing_policy.category, selected_workers=selected_ids
    )
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

    await emit_run_step(
        step_id='orc_checklist_validation',
        phase='orc',
        agent_id='orc',
        status='completed',
        title='主席团 checklist 校验通过',
        summary=_clean_inline('Checklist draft passed schema and self-check validation; ready to dispatch agents.', limit=110),
        meta={
            'selected_workers': selected_ids,
            'checklist_items': [item.model_dump() for item in validated_checklist],
            'checklist_self_check': validated_self_check.model_dump(),
        },
    )
    await emit_run_step(
        step_id='orc_selected_workers',
        phase='orc',
        agent_id='orc',
        status='completed',
        title=_build_selected_worker_title(selected_ids, worker_map),
        summary=_build_selected_worker_summary(tasks, routing_policy),
        meta={
            'selected_workers': selected_ids,
            'route': routing_policy.category,
            'checklist_items': [item.model_dump() for item in validated_checklist],
            'checklist_self_check': validated_self_check.model_dump(),
        },
    )

    # Hand off to the StateGraph workflow.
    turn_id = current_turn_id() or current_message_id() or ""
    content, artifact = await run_delegate_workflow(
        user_question=user_question,
        routing_policy_dict=asdict(routing_policy),
        selected_ids=selected_ids,
        tasks=tasks,
        worker_map=worker_map,
        critic_dept=critic_agent,
        validated_checklist=validated_checklist,
        turn_id=turn_id,
        deliverable_type_id=(deliverable_type_id or "").strip() or None,
    )

    # Fold the self-check into the final artifact (workflow doesn't know about it).
    artifact['checklist_self_check'] = validated_self_check.model_dump()
    return content, artifact
