"""LangGraph StateGraph that orchestrates the delegate workflow.

Replaces the imperative `delegate_to_departments` body with an explicit
graph:

    START
      ↓
    [dispatch_workers] ──Send──→ [run_worker × N]
                                       ↓
                                   [aggregate_workers]
                                       ↓
                                   [run_critic]
                                       ↓
                                   [decide_rework] ──fixes_required──→
                                       ↓ pass / failed                   ↓
                                       │                            [dispatch_rework]
                                       │                                  │
                                       │                            ─Send─→ [run_rework_worker × M]
                                       │                                        ↓
                                       │                            [aggregate_rework]
                                       │                                        ↓
                                       │                            [run_critic_recheck]
                                       │                                        │
                                       │←───────────────────────────────────────┘
                                       ↓
                                   [finalize]
                                       ↓
                                      END

Why a graph rather than `asyncio.gather`:
- The topology IS the documentation of how delegation flows
- Future LangGraph checkpointer can resume mid-workflow on crash
- Each node is independently observable / testable
- Conditional routing (rework vs finalize) is declarative, not buried in if/else

Behaviourally identical to the previous imperative pipeline. All event
emission, OrcSessionState mutation, and artifact construction happen
inside the nodes so observers see the same stream.
"""

from __future__ import annotations

import json
import logging
import operator
from dataclasses import asdict
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from runtime_events import current_session_id, emit_run_step
from session.checklist import (
    emit_checklist_sync,
    parse_validation_report,
    set_validation_report,
    update_checklist_item,
    upsert_artifact,
    upsert_worker_shard,
)
from subagents.executor import run_single_department, _run_department  # noqa: F401
from subagents.task_packet import WorkerTaskPacket

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class WorkflowState(TypedDict, total=False):
    """State accumulated across all nodes of the delegate graph."""

    # Inputs (set at invocation)
    user_question: str
    routing_policy: dict[str, Any]
    selected_ids: list[str]
    tasks: dict[str, WorkerTaskPacket]
    worker_map: dict[str, Any]  # dept_id → SubagentConfig
    critic_dept: Any  # SubagentConfig | None
    validated_checklist: list[Any]

    # Idempotency anchors — persisted by checkpointer so replays use the
    # same identifiers as the original run.
    turn_id: str
    attempt_number: int  # bumped on every rework round

    # Optional template id for deliverable-aware critic review
    deliverable_type_id: str

    # Accumulated outputs — reducers merge concurrent Send results
    worker_results: Annotated[list[Any], operator.add]
    worker_output_parts: Annotated[list[str], operator.add]
    department_results: Annotated[list[dict], operator.add]

    # Critic Phase 1
    critic_result: Any
    validation_report: Any

    # Rework loop
    rework_pairs: list[tuple[str, str]]
    rework_results: Annotated[list[Any], operator.add]
    rework_output_parts: Annotated[list[str], operator.add]

    # Final
    content: str
    artifact: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers (mirror what tools.py used to do inline)
# ---------------------------------------------------------------------------

def _clean_inline(text: str | None, limit: int = 120) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _serialize_result(result, *, phase: str, packet: WorkerTaskPacket | None, available_kb_refs: list[str] | None = None) -> dict:
    return {
        "id": result.id,
        "name": result.name,
        "display_name": result.display_name,
        "phase": phase,
        "task_packet": packet.model_dump() if packet else None,
        "available_kb_refs": available_kb_refs or [],
        "status": result.status,
        "content": result.content,
        "error": result.error,
        "startedAt": result.started_at.isoformat() if result.started_at else None,
        "completedAt": result.completed_at.isoformat() if result.completed_at else None,
    }


def _build_output_section(result) -> str:
    header = f"## {result.name}"
    if result.status == "completed":
        return f"{header}\n{result.content}"
    if result.status == "timed_out":
        return f"{header}\nTimed out: {result.error}"
    if result.status == "failed":
        return f"{header}\nFailed: {result.error}"
    return f"{header}\nStatus: {result.status}"


def _build_rework_packet(agent_id: str, packet: WorkerTaskPacket, feedback: str) -> WorkerTaskPacket:
    revised_task = (
        f"Revise the previous output for {agent_id}. Original task: {packet.task}\n\n"
        f"Critic-required fixes:\n- {feedback}\n\n"
        "Return an updated result that directly addresses the critic feedback."
    )
    return packet.model_copy(update={
        "task": revised_task,
        "notes": [*packet.notes, f"Critic feedback: {feedback}"],
        "success_criteria": [*packet.success_criteria, f"Explicitly resolve critic feedback: {feedback}"],
        "priority": "high",
    })


_PER_WORKER_OUTPUT_LIMIT = 3500
_PER_PACKET_FIELD_LIMIT = 800
_MAX_TASK_LEN = 14000


def _truncate_worker_summary(worker_summary: str, *, per_worker_limit: int = _PER_WORKER_OUTPUT_LIMIT) -> str:
    """Critic 1st-round inputs can hit proxy 16K body limits and 403.

    Worker outputs are joined by `\n\n---\n\n`. We split them back, cap
    each one to `per_worker_limit` chars (keep head + small tail so
    conclusions aren't lost), and rejoin. This is a tactical guardrail —
    the proper fix is to attach worker outputs as separate SystemMessages
    via WorkerTaskPacket.attached_history, but that requires a packet
    schema change.
    """
    parts = worker_summary.split("\n\n---\n\n")
    out_parts: list[str] = []
    for part in parts:
        if len(part) <= per_worker_limit:
            out_parts.append(part)
            continue
        head_len = max(0, per_worker_limit - 600)
        head = part[:head_len].rstrip()
        tail = part[-500:].lstrip()
        out_parts.append(f"{head}\n\n...[truncated {len(part) - per_worker_limit} chars]...\n\n{tail}")
    return "\n\n---\n\n".join(out_parts)


def _compact_packets(tasks: dict[str, WorkerTaskPacket]) -> dict:
    """Trim verbose fields in chairman packets so critic input stays small."""
    out: dict[str, dict] = {}
    for aid, packet in tasks.items():
        d = packet.model_dump()
        for k in ("task", "objective", "context", "notes"):
            v = d.get(k)
            if isinstance(v, str) and len(v) > _PER_PACKET_FIELD_LIMIT:
                d[k] = v[:_PER_PACKET_FIELD_LIMIT - 20] + "...[truncated]"
            elif isinstance(v, list):
                d[k] = [
                    (item[:_PER_PACKET_FIELD_LIMIT - 20] + "...[truncated]")
                    if isinstance(item, str) and len(item) > _PER_PACKET_FIELD_LIMIT
                    else item
                    for item in v
                ]
        out[aid] = d
    return out


def _build_critic_task(
    *,
    user_question: str,
    routing_policy: dict[str, Any],
    selected_ids: list[str],
    tasks: dict[str, WorkerTaskPacket],
    worker_map: dict[str, Any],
    worker_summary: str,
    review_round: int = 1,
    deliverable_type_id: str | None = None,
) -> str:
    round_label = "initial review" if review_round == 1 else f"review round {review_round}"
    kb_map = {aid: list(worker_map[aid].kb_refs) for aid in selected_ids if aid in worker_map}
    # Use compact (no-indent) JSON + per-field truncation to keep total
    # body below proxy limits (~16KB observed). See _truncate_worker_summary
    # and _compact_packets for the trimming strategy.
    truncated_outputs = _truncate_worker_summary(worker_summary)
    packets_json = json.dumps(_compact_packets(tasks), ensure_ascii=False)
    kb_json = json.dumps(kb_map, ensure_ascii=False)

    # If orc declared a deliverable_type, render its quality_gates so the
    # critic reviews against the right checklist instead of generic prose.
    deliverable_section = ""
    if deliverable_type_id:
        try:
            from deliverables.registry import get_deliverable_type
            dt = get_deliverable_type(deliverable_type_id)
            if dt is not None:
                gates = [str(g) for g in (getattr(dt, "quality_gates", []) or [])]
                name = getattr(dt, "name", "") or deliverable_type_id
                if gates:
                    gates_text = "\n".join(f"- {g}" for g in gates)
                    deliverable_section = (
                        f"[Deliverable type]\n{deliverable_type_id} ({name})\n\n"
                        f"[Deliverable quality gates — grade against these explicitly]\n{gates_text}\n\n"
                    )
        except Exception as exc:
            logger.warning("failed to render deliverable quality gates: %s", exc)

    task = (
        "Review the worker results as the single validation authority for this run.\n\n"
        f"[Review round]\n{round_label}\n\n"
        f"[User question]\n{user_question}\n\n"
        f"[Routing category]\n{routing_policy.get('category', '')}\n\n"
        f"[Routing rationale]\n{routing_policy.get('rationale', '')}\n\n"
        f"[Selected agents]\n{', '.join(selected_ids)}\n\n"
        f"{deliverable_section}"
        f"[Chairman task packets]\n{packets_json}\n\n"
        f"[Agent authorised KBs]\n{kb_json}\n\n"
        f"[Agent outputs]\n{truncated_outputs}\n\n"
        "Validate not only the text conclusions but also any referenced artifacts or deliverables. "
        "Focus on conflict, omission, execution risk, delivery quality, and whether the result can be shipped to the user. "
        + ("If a Deliverable quality gates list is present above, your <validation_report> summary must explicitly state which gates passed and which failed.\n" if deliverable_section else "")
        + "You must end with a <validation_report> block using pass_gate, summary, and rework_targets."
    )
    # Final hard cap on total task length — if we still exceeded budget
    # despite per-worker truncation (e.g. very long packet metadata), trim
    # from the worker outputs section since that's the most expendable.
    # The replacement marker itself is ~70 chars, so cut enough to absorb
    # both the overflow AND the marker length.
    if len(task) > _MAX_TASK_LEN:
        sentinel = "[Agent outputs]\n"
        idx = task.find(sentinel)
        if idx >= 0:
            marker = "...[outputs further truncated to fit critic budget]...\n\n"
            overflow = len(task) - _MAX_TASK_LEN
            cut_chars = overflow + len(marker) + 32  # buffer
            cut_start = idx + len(sentinel)
            cut_end = cut_start + cut_chars
            task = task[:cut_start] + marker + task[cut_end:]
    return task


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def dispatch_workers(state: WorkflowState) -> dict:
    """Phase 1 entry. Emits the 'starting' event then fan-out via Send."""
    session_id = current_session_id()
    selected_ids = state["selected_ids"]
    logger.info("Phase 1: dispatching agents %s (route=%s)",
                selected_ids, state["routing_policy"].get("category"))
    if session_id:
        # checklist + emit was already done by the caller during validation
        # so this node only emits the "ready to dispatch" cursor event.
        pass
    return {}


def _fanout_workers(state: WorkflowState) -> list[Send]:
    """Conditional edge — emit one Send per selected worker."""
    attempt = state.get("attempt_number", 1)
    return [
        Send("run_worker", {
            "agent_id": aid,
            "packet": state["tasks"][aid],
            "dept": state["worker_map"][aid],
            "attempt_number": attempt,
        })
        for aid in state["selected_ids"]
    ]


async def run_worker(node_input: dict) -> dict:
    """Run a single worker. Reducer on state will merge results back."""
    aid = node_input["agent_id"]
    packet: WorkerTaskPacket = node_input["packet"]
    dept = node_input["dept"]
    attempt_number = node_input.get("attempt_number", 1)
    result = await _run_department(dept, packet, attempt_number=attempt_number)
    return {
        "worker_results": [result],
        "worker_output_parts": [_build_output_section(result)],
        "department_results": [
            _serialize_result(result, phase="worker", packet=packet, available_kb_refs=list(dept.kb_refs))
        ],
    }


async def aggregate_workers(state: WorkflowState) -> dict:
    """Phase 1 join. All Send results have been merged via reducers."""
    parts = state.get("worker_output_parts", [])
    summary = "\n\n---\n\n".join(parts) if parts else "(No agent output)"
    logger.info("Phase 1 aggregate: %d worker result(s) collected", len(state.get("worker_results", [])))
    return {"_worker_summary": summary}  # not in TypedDict; passed via dict, ignored by reducer


async def run_critic(state: WorkflowState) -> dict:
    """Phase 2: run critic on aggregated worker output."""
    critic_dept = state.get("critic_dept")
    if critic_dept is None:
        logger.warning("No critic agent (crt) found, skipping review phase")
        return {"critic_result": None, "validation_report": None}

    session_id = current_session_id()
    turn_id = state.get("turn_id", "")
    attempt_number = state.get("attempt_number", 1)
    worker_summary = "\n\n---\n\n".join(state.get("worker_output_parts", [])) or "(No agent output)"

    await emit_run_step(
        step_id="critic_review_phase_1",
        phase="critic",
        agent_id="crt",
        status="running",
        title="风控部开始评审",
        summary="整合所有 agent 的产出后由风控部做跨域审查与放行判断。",
        meta={"review_round": 1, "selected_workers": state["selected_ids"]},
    )
    if session_id:
        st = update_checklist_item(
            session_id, "critic_review",
            status="running",
            result_preview="Reviewing cross-agent conflicts, quality risks, and delivery readiness.",
        )
        await emit_checklist_sync(st)

    critic_result = await run_single_department(
        dept_id="crt",
        task=_build_critic_task(
            user_question=state["user_question"],
            routing_policy=state["routing_policy"],
            selected_ids=state["selected_ids"],
            tasks=state["tasks"],
            worker_map=state["worker_map"],
            worker_summary=worker_summary,
            review_round=1,
            deliverable_type_id=state.get("deliverable_type_id"),
        ),
        step_suffix="review1",
        attempt_number=attempt_number,
    )
    report = parse_validation_report(critic_result.content or critic_result.error, status=critic_result.status)

    await emit_run_step(
        step_id="critic_review_phase_1",
        phase="critic",
        agent_id="crt",
        status="completed" if critic_result.status == "completed" else "failed",
        title="风控部完成评审",
        summary=_clean_inline(report.summary or critic_result.content or critic_result.error or critic_result.status, limit=120),
        meta={"review_round": 1, "pass_gate": report.pass_gate},
    )
    if session_id:
        st = set_validation_report(session_id, report)
        st = update_checklist_item(
            session_id, "critic_review",
            status="done" if critic_result.status == "completed" else "failed",
            result_preview=report.summary or critic_result.content or critic_result.error or critic_result.status,
            result_ref="crt",
            verification_status=report.pass_gate,
        )
        st = upsert_artifact(
            session_id,
            artifact_id=f"{turn_id}:crt:validation_report:{attempt_number}",
            owner="crt",
            kind="validation_report",
            content=report.raw_text or (critic_result.content or critic_result.error or ""),
            linked_checklist_item="critic_review",
        )
        for finding in report.rework_targets:
            if finding.owner in state["worker_map"]:
                st = upsert_worker_shard(
                    session_id, finding.owner,
                    validation_feedback=finding.summary,
                    status="needs_rework" if report.pass_gate != "passed" else "validated",
                )
        await emit_checklist_sync(st)

    return {
        "critic_result": critic_result,
        "validation_report": report,
        "department_results": [_serialize_result(critic_result, phase="critic", packet=None)],
    }


def decide_rework(state: WorkflowState) -> str:
    """Conditional edge: rework or finalize?"""
    report = state.get("validation_report")
    if report is None:
        return "finalize"
    if report.pass_gate != "fixes_required" or not report.rework_targets:
        return "finalize"
    pairs = [(f.owner, f.summary) for f in report.rework_targets if f.owner in state["tasks"]]
    if not pairs:
        return "finalize"
    return "dispatch_rework"


async def dispatch_rework(state: WorkflowState) -> dict:
    """Emit rework events + update shards. Then fan-out via Send."""
    session_id = current_session_id()
    report = state["validation_report"]
    pairs = [(f.owner, f.summary) for f in report.rework_targets if f.owner in state["tasks"]]
    next_attempt = state.get("attempt_number", 1) + 1
    await emit_run_step(
        step_id="orc_rework_dispatch",
        phase="orc",
        agent_id="orc",
        status="running",
        title="主席团根据风控意见返工",
        summary=_clean_inline("; ".join(f"{o}: {fb}" for o, fb in pairs), limit=120),
        meta={"rework_targets": [o for o, _ in pairs], "attempt": next_attempt},
    )

    # Build new rework packets and stash on state
    new_tasks = dict(state["tasks"])
    for owner, feedback in pairs:
        new_tasks[owner] = _build_rework_packet(owner, new_tasks[owner], feedback)
        if session_id:
            st = upsert_worker_shard(
                session_id, owner,
                task_packet=new_tasks[owner].model_dump(),
                validation_feedback=feedback,
                attempt_number=next_attempt,
                status="reworking",
            )
            await emit_checklist_sync(st)

    return {"tasks": new_tasks, "rework_pairs": pairs, "attempt_number": next_attempt}


def _fanout_rework(state: WorkflowState) -> list[Send]:
    pairs = state.get("rework_pairs", [])
    attempt = state.get("attempt_number", 1)
    return [
        Send("run_rework_worker", {
            "agent_id": owner,
            "packet": state["tasks"][owner],
            "dept": state["worker_map"][owner],
            "index": i,
            "attempt_number": attempt,
        })
        for i, (owner, _) in enumerate(pairs, start=1)
    ]


async def run_rework_worker(node_input: dict) -> dict:
    aid = node_input["agent_id"]
    packet: WorkerTaskPacket = node_input["packet"]
    dept = node_input["dept"]
    idx = node_input["index"]
    attempt_number = node_input.get("attempt_number", 1)
    result = await run_single_department(
        dept_id=aid,
        task=packet.task,
        task_packet=packet,
        step_suffix=f"rework{idx}",
        attempt_number=attempt_number,
    )
    return {
        "rework_results": [result],
        "rework_output_parts": [_build_output_section(result)],
        "department_results": [
            _serialize_result(result, phase="worker", packet=packet, available_kb_refs=list(dept.kb_refs))
        ],
    }


async def aggregate_rework(state: WorkflowState) -> dict:
    """Replace original worker sections (for reworked owners) with new versions."""
    rework_pairs = state.get("rework_pairs", [])
    rework_owner_names = {state["worker_map"][o].name for o, _ in rework_pairs if o in state["worker_map"]}
    original = state.get("worker_output_parts", [])
    kept = [s for s in original if not any(s.startswith(f"## {name}") for name in rework_owner_names)]
    merged = kept + state.get("rework_output_parts", [])
    return {"_worker_summary_after_rework": "\n\n---\n\n".join(merged) if merged else "(No agent output)"}


async def run_critic_recheck(state: WorkflowState) -> dict:
    session_id = current_session_id()
    turn_id = state.get("turn_id", "")
    attempt_number = state.get("attempt_number", 1)
    rework_pairs = state.get("rework_pairs", [])
    # Use the merged output (originals minus replaced + reworked)
    rework_owner_names = {state["worker_map"][o].name for o, _ in rework_pairs if o in state["worker_map"]}
    original = state.get("worker_output_parts", [])
    kept = [s for s in original if not any(s.startswith(f"## {name}") for name in rework_owner_names)]
    merged_sections = kept + state.get("rework_output_parts", [])
    worker_summary = "\n\n---\n\n".join(merged_sections) if merged_sections else "(No agent output)"

    await emit_run_step(
        step_id="critic_review_phase_2",
        phase="critic",
        agent_id="crt",
        status="running",
        title="风控部进行二次复核",
        summary="对返工后的产出进行二次复核与放行判断。",
        meta={"review_round": 2, "rework_targets": [o for o, _ in rework_pairs]},
    )

    critic_result = await run_single_department(
        dept_id="crt",
        task=_build_critic_task(
            user_question=state["user_question"],
            routing_policy=state["routing_policy"],
            selected_ids=state["selected_ids"],
            tasks=state["tasks"],
            worker_map=state["worker_map"],
            worker_summary=worker_summary,
            review_round=2,
            deliverable_type_id=state.get("deliverable_type_id"),
        ),
        step_suffix="review2",
        attempt_number=attempt_number,
    )
    report = parse_validation_report(critic_result.content or critic_result.error, status=critic_result.status)
    await emit_run_step(
        step_id="critic_review_phase_2",
        phase="critic",
        agent_id="crt",
        status="completed" if critic_result.status == "completed" else "failed",
        title="风控部二次复核完成",
        summary=_clean_inline(report.summary or critic_result.content or critic_result.error or critic_result.status, limit=120),
        meta={"review_round": 2, "pass_gate": report.pass_gate},
    )
    if session_id:
        st = set_validation_report(session_id, report)
        st = update_checklist_item(
            session_id, "critic_review",
            status="done" if critic_result.status == "completed" else "failed",
            result_preview=report.summary or critic_result.content or critic_result.error or critic_result.status,
            result_ref="crt",
            verification_status=report.pass_gate,
        )
        st = upsert_artifact(
            session_id,
            artifact_id=f"{turn_id}:crt:validation_report_recheck:{attempt_number}",
            owner="crt",
            kind="validation_report_recheck",
            content=report.raw_text or (critic_result.content or critic_result.error or ""),
            linked_checklist_item="critic_review",
        )
        for owner, feedback in rework_pairs:
            st = upsert_worker_shard(
                session_id, owner,
                validation_feedback=feedback,
                status="validated" if report.pass_gate == "passed" else "needs_rework",
            )
        await emit_checklist_sync(st)

    return {
        "critic_result": critic_result,
        "validation_report": report,
        "department_results": [_serialize_result(critic_result, phase="critic", packet=None)],
    }


async def finalize(state: WorkflowState) -> dict:
    """Assemble final `content` string and `artifact` dict."""
    session_id = current_session_id()
    critic_result = state.get("critic_result")
    report = state.get("validation_report")

    # Recompute the post-rework merged summary if applicable
    rework_pairs = state.get("rework_pairs", [])
    if rework_pairs:
        rework_owner_names = {state["worker_map"][o].name for o, _ in rework_pairs if o in state["worker_map"]}
        original = state.get("worker_output_parts", [])
        kept = [s for s in original if not any(s.startswith(f"## {name}") for name in rework_owner_names)]
        merged = kept + state.get("rework_output_parts", [])
    else:
        merged = state.get("worker_output_parts", [])
    worker_summary = "\n\n---\n\n".join(merged) if merged else "(No agent output)"

    if critic_result is not None:
        critic_header = f"## {critic_result.name} - Validation Review"
        critic_section = (
            f"{critic_header}\n{critic_result.content}"
            if critic_result.status == "completed"
            else f"{critic_header}\nReview failed: {critic_result.error or critic_result.status}"
        )
        content = f"{worker_summary}\n\n{'=' * 40}\n\n{critic_section}"
    else:
        content = worker_summary

    if session_id:
        st = update_checklist_item(
            session_id, "orc_final",
            status="running",
            result_preview="Assembling the final answer for the user.",
        )
        await emit_checklist_sync(st)

    await emit_run_step(
        step_id="orc_finalizing",
        phase="final",
        agent_id="orc",
        status="running",
        title="主席团正在整合并准备最终答复",
        summary="收集所有 agent 产出与风控结论，准备给用户的最终交付。",
        meta={
            "selected_workers": state["selected_ids"],
            "validation_gate": report.pass_gate if report else "unknown",
        },
    )

    artifact = {
        "user_question": state["user_question"],
        "routing_policy": state["routing_policy"],
        "chairman_plan": {aid: p.model_dump() for aid, p in state["tasks"].items()},
        "checklist_draft": [item.model_dump() for item in state["validated_checklist"]],
        "validation_report": report.model_dump() if report else None,
        "selected_workers": state["selected_ids"],
        "department_results": state.get("department_results", []),
    }
    return {"content": content, "artifact": artifact}


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_delegate_graph(*, checkpointer: Any = None):
    """Compile the delegate workflow graph.

    Compiled once per checkpointer instance (see `_GRAPH` below) — the
    same compiled instance handles every `delegate_to_departments` call.
    Pass `checkpointer` to enable crash-resumption via LangGraph thread
    state; node-level side effects (event emission, OrcSessionState
    writes) are designed to be idempotent across replays.
    """
    g: StateGraph = StateGraph(WorkflowState)

    g.add_node("dispatch_workers", dispatch_workers)
    g.add_node("run_worker", run_worker)
    g.add_node("aggregate_workers", aggregate_workers)
    g.add_node("run_critic", run_critic)
    g.add_node("dispatch_rework", dispatch_rework)
    g.add_node("run_rework_worker", run_rework_worker)
    g.add_node("aggregate_rework", aggregate_rework)
    g.add_node("run_critic_recheck", run_critic_recheck)
    g.add_node("finalize", finalize)

    g.add_edge(START, "dispatch_workers")
    g.add_conditional_edges("dispatch_workers", _fanout_workers, ["run_worker"])
    g.add_edge("run_worker", "aggregate_workers")
    g.add_edge("aggregate_workers", "run_critic")

    g.add_conditional_edges(
        "run_critic",
        decide_rework,
        {"dispatch_rework": "dispatch_rework", "finalize": "finalize"},
    )
    g.add_conditional_edges("dispatch_rework", _fanout_rework, ["run_rework_worker"])
    g.add_edge("run_rework_worker", "aggregate_rework")
    g.add_edge("aggregate_rework", "run_critic_recheck")
    g.add_edge("run_critic_recheck", "finalize")
    g.add_edge("finalize", END)

    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)
    return g.compile()


_GRAPH = None
_CHECKPOINTER: Any = None


def set_delegate_checkpointer(checkpointer: Any) -> None:
    """Inject the AsyncSqliteSaver (or any LangGraph checkpointer) for the
    delegate graph. Called by `app/main.py`'s FastAPI lifespan. Resets the
    compiled singleton so the next `get_delegate_graph()` rebuilds with the
    new checkpointer bound.
    """
    global _CHECKPOINTER, _GRAPH
    _CHECKPOINTER = checkpointer
    _GRAPH = None


def get_delegate_graph():
    """Lazy singleton — compiled with the currently registered checkpointer.

    If no checkpointer has been registered yet (e.g. tests, scripts), the
    graph is compiled without one and crash recovery is disabled — but the
    workflow still runs end-to-end as a one-shot.
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_delegate_graph(checkpointer=_CHECKPOINTER)
    return _GRAPH


async def run_delegate_workflow(
    *,
    user_question: str,
    routing_policy_dict: dict[str, Any],
    selected_ids: list[str],
    tasks: dict[str, WorkerTaskPacket],
    worker_map: dict[str, Any],
    critic_dept: Any,
    validated_checklist: list[Any],
    turn_id: str = "",
    deliverable_type_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Invoke the compiled graph and return `(content, artifact)`.

    Mirrors the public contract that `delegate_to_departments` exposes
    as a LangChain tool — so the tool body collapses to "validate input,
    call this, return result".

    `turn_id` is the per-request identifier (typically the lead agent's
    message_id). It is plumbed into the graph state so that side-effect
    keys (artifact ids, dedup keys, checkpoint thread ids) are stable
    across replays of the same request.
    """
    graph = get_delegate_graph()
    initial_state: WorkflowState = {
        "user_question": user_question,
        "routing_policy": routing_policy_dict,
        "selected_ids": selected_ids,
        "tasks": tasks,
        "worker_map": worker_map,
        "critic_dept": critic_dept,
        "validated_checklist": validated_checklist,
        "turn_id": turn_id,
        "attempt_number": 1,
        "deliverable_type_id": deliverable_type_id or "",
        "worker_results": [],
        "worker_output_parts": [],
        "department_results": [],
        "rework_results": [],
        "rework_output_parts": [],
    }
    session_id = current_session_id() or "anon"
    thread_key = turn_id or "no-turn"
    config = {"configurable": {"thread_id": f"delegate::{session_id}::{thread_key}"}}
    final_state = await graph.ainvoke(initial_state, config=config)
    return final_state.get("content", ""), final_state.get("artifact", {})
