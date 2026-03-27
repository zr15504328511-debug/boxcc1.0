from __future__ import annotations

import uuid
from collections import defaultdict, deque
from typing import Iterable

from pydantic import BaseModel, Field, ValidationError

from runtime_events import emit_event
from session.state import ChecklistItem, OrcSessionState, TaskArtifact, ValidationFinding, ValidationReport, WorkerShard
from session.store import get_session_store


_ALLOWED_OWNERS = {"orc", "dom", "pln", "ana", "cpy", "crt", "system"}
_VERIFY_STEP_OWNERS = {"crt", "system"}
_WORKER_OWNERS = {"dom", "pln", "ana", "cpy"}

INTAKE_ITEM_ID = "orc_intake"
VERIFY_ITEM_ID = "critic_review"
FINAL_ITEM_ID = "orc_final"

INTAKE_TITLE = '主席团分析问题并拆解任务'
VERIFY_TITLE = '质检部复核关键风险与交付质量'
FINAL_TITLE = '主席团整合验证结论并返回结果'

_TITLE_MAP = {
    "dom": '学术部分析风险与工艺',
    "pln": '企划部整理开发方案与规避动作',
    "ana": '经营部核算成本与经营指标',
    "cpy": '宣传部整理表达与传播输出',
}


class ChecklistDraftItem(BaseModel):
    item_id: str
    title: str
    owner: str
    depends_on: list[str] = Field(default_factory=list)


class ChecklistSelfCheck(BaseModel):
    passed: bool
    issues: list[str] | str = Field(default_factory=list)
    fixes: list[str] | str = Field(default_factory=list)
    selected_workers: list[str] | str = Field(default_factory=list)


def _clean_inline(text: str | None, limit: int = 96) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _dedupe(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _is_placeholder_title(title: str | None) -> bool:
    stripped = "".join(str(title or "").split())
    if not stripped:
        return True
    if set(stripped) <= {"?", "?", "-", "_", "."}:
        return True
    if stripped.count('?') + stripped.count('?') >= 2:
        return True
    if '?' in stripped or '?' in stripped or '?' in stripped:
        return True
    return False


def _default_title(owner: str, *, item_id: str = "") -> str:
    if owner == "orc":
        return FINAL_TITLE if item_id.startswith(FINAL_ITEM_ID) else INTAKE_TITLE
    if owner in _WORKER_OWNERS:
        return _TITLE_MAP.get(owner, owner)
    if owner in _VERIFY_STEP_OWNERS or item_id.startswith("verify") or item_id.startswith("critic"):
        return VERIFY_TITLE
    return item_id or owner or '执行任务'


def _normalize_title(title: str | None, *, owner: str, item_id: str) -> str:
    if _is_placeholder_title(title):
        return _default_title(owner, item_id=item_id)
    return str(title).strip()


def build_initial_checklist(session_id: str, user_question: str, route: str, suggested_workers: Iterable[str]) -> list[ChecklistItem]:
    del session_id, user_question
    workers = _dedupe(suggested_workers)
    items = [
        ChecklistItem(item_id=INTAKE_ITEM_ID, title=INTAKE_TITLE, owner="orc", status="running"),
    ]
    for worker_id in workers:
        items.append(
            ChecklistItem(
                item_id=f"worker_{worker_id}",
                title=_TITLE_MAP.get(worker_id, worker_id),
                owner=worker_id,
                status="pending",
                depends_on=[INTAKE_ITEM_ID],
            )
        )
    needs_verify = route != "direct_answer" and bool(workers)
    if needs_verify:
        items.append(
            ChecklistItem(
                item_id=VERIFY_ITEM_ID,
                title=VERIFY_TITLE,
                owner="crt",
                status="pending",
                depends_on=[item.item_id for item in items if item.owner in _WORKER_OWNERS],
            )
        )
    items.append(
        ChecklistItem(
            item_id=FINAL_ITEM_ID,
            title=FINAL_TITLE,
            owner="orc",
            status="pending",
            depends_on=[VERIFY_ITEM_ID] if needs_verify else [INTAKE_ITEM_ID],
        )
    )
    return items


def _normalize_checklist_items(raw: object) -> list[ChecklistDraftItem]:
    if isinstance(raw, dict):
        raw = raw.get("items")
    if not isinstance(raw, list):
        raise ValueError("checklist_draft must be a JSON array of checklist items or an object with an 'items' array.")
    items: list[ChecklistDraftItem] = []
    errors: list[str] = []
    for idx, item in enumerate(raw):
        try:
            validated = ChecklistDraftItem.model_validate(item)
            validated.title = _normalize_title(validated.title, owner=validated.owner, item_id=validated.item_id)
            validated.depends_on = _dedupe(dep for dep in validated.depends_on if dep and dep != validated.item_id)
            items.append(validated)
        except ValidationError as exc:
            errors.append(f"item {idx + 1}: {exc.errors()}")
    if errors:
        raise ValueError(" ; ".join(errors))
    return items


def _assert_no_cycles(items: list[ChecklistDraftItem]) -> None:
    indegree = {item.item_id: 0 for item in items}
    graph: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for dep in item.depends_on:
            graph[dep].append(item.item_id)
            indegree[item.item_id] += 1
    queue = deque([node for node, degree in indegree.items() if degree == 0])
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in graph.get(node, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(items):
        raise ValueError("checklist_draft contains circular dependencies.")


def _coerce_checklist_structure(draft_items: list[ChecklistDraftItem], *, route: str, selected_workers: list[str]) -> list[ChecklistDraftItem]:
    items = [item.model_copy(deep=True) for item in draft_items]
    ids = {item.item_id for item in items}

    if not items or items[0].owner != "orc":
        if INTAKE_ITEM_ID not in ids:
            items.insert(0, ChecklistDraftItem(item_id=INTAKE_ITEM_ID, title=INTAKE_TITLE, owner="orc", depends_on=[]))
            ids.add(INTAKE_ITEM_ID)
        else:
            intake = next(item for item in items if item.item_id == INTAKE_ITEM_ID)
            items = [intake, *[item for item in items if item.item_id != INTAKE_ITEM_ID]]
            intake.title = INTAKE_TITLE
            intake.owner = "orc"
            intake.depends_on = []

    if INTAKE_ITEM_ID not in ids:
        items.insert(0, ChecklistDraftItem(item_id=INTAKE_ITEM_ID, title=INTAKE_TITLE, owner="orc", depends_on=[]))
        ids.add(INTAKE_ITEM_ID)

    worker_item_ids: list[str] = [item.item_id for item in items if item.owner in _WORKER_OWNERS]
    existing_worker_owners = {item.owner for item in items if item.owner in _WORKER_OWNERS}
    for worker in selected_workers:
        if worker not in existing_worker_owners:
            worker_item_id = f"worker_{worker}"
            suffix = 2
            while worker_item_id in ids:
                worker_item_id = f"worker_{worker}_{suffix}"
                suffix += 1
            items.append(
                ChecklistDraftItem(
                    item_id=worker_item_id,
                    title=_TITLE_MAP.get(worker, worker),
                    owner=worker,
                    depends_on=[INTAKE_ITEM_ID],
                )
            )
            ids.add(worker_item_id)
            worker_item_ids.append(worker_item_id)

    for item in items:
        item.title = _normalize_title(item.title, owner=item.owner, item_id=item.item_id)
        if item.owner == "orc" and item.item_id == INTAKE_ITEM_ID:
            item.title = INTAKE_TITLE
            item.depends_on = []
        elif item.owner in _WORKER_OWNERS and not item.depends_on:
            item.depends_on = [INTAKE_ITEM_ID]
        elif item.owner in _VERIFY_STEP_OWNERS or item.item_id.startswith("verify") or item.item_id.startswith("critic"):
            item.title = VERIFY_TITLE
            if route != "direct_answer" and selected_workers:
                item.depends_on = _dedupe(worker_item_ids or [INTAKE_ITEM_ID])
        elif item.owner == "orc" and item.item_id.startswith(FINAL_ITEM_ID):
            item.title = FINAL_TITLE

    has_verify_owner = any(item.owner in _VERIFY_STEP_OWNERS or item.item_id.startswith("verify") or item.item_id.startswith("critic") for item in items)
    if route != "direct_answer" and selected_workers and not has_verify_owner:
        verify_id = VERIFY_ITEM_ID
        suffix = 2
        while verify_id in ids:
            verify_id = f"{VERIFY_ITEM_ID}_{suffix}"
            suffix += 1
        items.append(
            ChecklistDraftItem(
                item_id=verify_id,
                title=VERIFY_TITLE,
                owner="crt",
                depends_on=_dedupe(worker_item_ids or [INTAKE_ITEM_ID]),
            )
        )
        ids.add(verify_id)

    final_candidates = [item for item in items if item.owner == "orc" and item.item_id.startswith(FINAL_ITEM_ID)]
    if final_candidates:
        final_item = final_candidates[-1]
    else:
        final_item = ChecklistDraftItem(item_id=FINAL_ITEM_ID, title=FINAL_TITLE, owner="orc", depends_on=[VERIFY_ITEM_ID] if route != "direct_answer" and selected_workers else [INTAKE_ITEM_ID])

    intake_item = ChecklistDraftItem(item_id=INTAKE_ITEM_ID, title=INTAKE_TITLE, owner="orc", depends_on=[])

    canonical_worker_items: list[ChecklistDraftItem] = []
    for worker in selected_workers:
        source = next((item for item in items if item.owner == worker), None)
        canonical_worker_items.append(
            ChecklistDraftItem(
                item_id=f"worker_{worker}",
                title=_normalize_title(source.title if source else "", owner=worker, item_id=f"worker_{worker}"),
                owner=worker,
                depends_on=[INTAKE_ITEM_ID],
            )
        )

    canonical_items = [intake_item, *canonical_worker_items]

    if route != "direct_answer" and selected_workers:
        verify_item = next((item for item in items if item.owner in _VERIFY_STEP_OWNERS or item.item_id.startswith("verify") or item.item_id.startswith("critic")), None)
        canonical_items.append(
            ChecklistDraftItem(
                item_id=VERIFY_ITEM_ID,
                title=_normalize_title(verify_item.title if verify_item else "", owner="crt", item_id=VERIFY_ITEM_ID),
                owner="crt",
                depends_on=[f"worker_{worker}" for worker in selected_workers],
            )
        )
        final_depends = [VERIFY_ITEM_ID]
    else:
        final_depends = [INTAKE_ITEM_ID]

    canonical_items.append(
        ChecklistDraftItem(
            item_id=FINAL_ITEM_ID,
            title=FINAL_TITLE,
            owner="orc",
            depends_on=final_depends,
        )
    )

    return canonical_items


def validate_checklist_draft(raw: object, *, route: str, selected_workers: list[str]) -> list[ChecklistItem]:
    draft_items = _coerce_checklist_structure(_normalize_checklist_items(raw), route=route, selected_workers=selected_workers)
    if len(draft_items) < 3:
        raise ValueError("checklist_draft must contain at least 3 items.")
    if len(draft_items) > 10:
        raise ValueError("checklist_draft may contain at most 10 items after normalization.")

    ids = [item.item_id for item in draft_items]
    if len(ids) != len(set(ids)):
        raise ValueError("checklist_draft item_id values must be unique.")

    first_item = draft_items[0]
    last_item = draft_items[-1]
    if first_item.owner != "orc":
        raise ValueError("The first checklist item must belong to orc.")
    if last_item.owner != "orc":
        raise ValueError("The last checklist item must belong to orc.")

    id_set = set(ids)
    selected_set = set(selected_workers)
    owner_hits: dict[str, int] = defaultdict(int)
    verify_present = False
    for item in draft_items:
        if item.owner not in _ALLOWED_OWNERS:
            raise ValueError(f"checklist_draft owner '{item.owner}' is invalid.")
        owner_hits[item.owner] += 1
        for dep in item.depends_on:
            if dep not in id_set:
                raise ValueError(f"checklist_draft dependency '{dep}' does not exist.")
        if item.owner in _VERIFY_STEP_OWNERS or item.item_id.startswith("verify") or item.item_id.startswith("critic"):
            verify_present = True

    missing_worker_items = [worker for worker in selected_workers if owner_hits.get(worker, 0) == 0]
    if missing_worker_items:
        raise ValueError(f"checklist_draft is missing execution items for workers: {', '.join(missing_worker_items)}.")

    if route != "direct_answer" and selected_workers and not verify_present:
        raise ValueError("checklist_draft normalization failed to create a verify/review step for non-trivial work.")

    _assert_no_cycles(draft_items)

    normalized: list[ChecklistItem] = []
    first_running_assigned = False
    for item in draft_items:
        status = "pending"
        if not first_running_assigned and item.owner == "orc":
            status = "running"
            first_running_assigned = True
        normalized.append(
            ChecklistItem(
                item_id=item.item_id,
                title=item.title,
                owner=item.owner,
                status=status,
                depends_on=item.depends_on,
            )
        )

    unexpected_worker_items = sorted({item.owner for item in normalized if item.owner in _WORKER_OWNERS and item.owner not in selected_set})
    if unexpected_worker_items:
        raise ValueError(f"checklist_draft references workers not selected in chairman_plan: {', '.join(unexpected_worker_items)}.")
    return normalized


def validate_checklist_self_check(raw: object, *, selected_workers: list[str]) -> ChecklistSelfCheck:
    if not isinstance(raw, dict):
        raise ValueError("checklist_self_check must be a JSON object.")
    try:
        payload = ChecklistSelfCheck.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"checklist_self_check is invalid: {exc.errors()}") from exc
    normalized_workers = _dedupe(payload.selected_workers if isinstance(payload.selected_workers, list) else [payload.selected_workers])
    expected_workers = _dedupe(selected_workers)
    if sorted(normalized_workers) != sorted(expected_workers):
        raise ValueError(
            "checklist_self_check.selected_workers must exactly match the chairman_plan worker set: "
            f"expected {expected_workers}, got {normalized_workers}."
        )
    normalized_issues = payload.issues if isinstance(payload.issues, list) else ([payload.issues] if str(payload.issues).strip() else [])
    normalized_fixes = payload.fixes if isinstance(payload.fixes, list) else ([payload.fixes] if str(payload.fixes).strip() else [])
    return payload.model_copy(update={"selected_workers": expected_workers, "issues": normalized_issues, "fixes": normalized_fixes})


def build_orc_session_brief(state: OrcSessionState | None, *, current_user_message: str) -> str:
    if state is None:
        return ""
    has_meaningful_state = bool(state.execution_checklist or state.worker_shards or state.final_answer_summary or state.task_type or state.selected_workers)
    if not has_meaningful_state:
        return ""
    sections: list[str] = []
    if state.user_goal:
        sections.append(f"Primary goal: {_clean_inline(state.user_goal, limit=180)}")
    if state.task_type:
        sections.append(f"Last task type: {state.task_type}")
    if state.selected_workers:
        sections.append(f"Last selected workers: {', '.join(state.selected_workers)}")

    open_items = [item for item in state.execution_checklist if item.status in {"pending", "running", "failed"}]
    if open_items:
        lines = [f"- {item.title} [{item.status}]" for item in open_items[:5]]
        sections.append("Checklist snapshot:\n" + "\n".join(lines))

    shard_lines: list[str] = []
    for worker_id, shard in list(state.worker_shards.items())[:4]:
        summary = shard.validation_feedback or shard.result_summary or shard.latest_output
        if summary:
            shard_lines.append(f"- {worker_id}: {_clean_inline(summary, limit=160)}")
    if shard_lines:
        sections.append("Worker shard snapshot:\n" + "\n".join(shard_lines))

    if state.final_answer_summary:
        sections.append(f"Last final summary: {_clean_inline(state.final_answer_summary, limit=200)}")

    if not sections:
        return ""

    return (
        "<orc_session_summary>\n"
        "Use this as compressed task-state memory from the current session. Treat it as prior state, not as a new user request.\n\n"
        + "\n\n".join(sections)
        + "\n</orc_session_summary>\n\n"
        + "<current_user_request>\n"
        + str(current_user_message or "").strip()
        + "\n</current_user_request>"
    )


def sync_session_checklist(session_id: str, checklist: list[ChecklistItem], *, user_goal: str = "", task_type: str = "", selected_workers: list[str] | None = None, run_status: str | None = None) -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        if user_goal:
            state.user_goal = user_goal
        if task_type:
            state.task_type = task_type
        state.execution_checklist = checklist
        if selected_workers is not None:
            state.selected_workers = list(selected_workers)
        if run_status is not None:
            state.last_run_status = run_status
        return state

    return store.update(session_id, updater)


def update_checklist_item(session_id: str, item_id: str, *, status: str | None = None, result_preview: str | None = None, result_ref: str | None = None, verification_status: str | None = None) -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        for item in state.execution_checklist:
            if item.item_id != item_id:
                continue
            if status is not None:
                item.status = status
            if result_preview is not None:
                item.result_preview = _clean_inline(result_preview)
            if result_ref is not None:
                item.result_ref = result_ref
            if verification_status is not None:
                item.verification_status = verification_status
            break
        return state

    return store.update(session_id, updater)


def upsert_worker_shard(session_id: str, worker_id: str, *, task_packet: dict | None = None, latest_output: str | None = None, result_summary: str | None = None, validation_feedback: str | None = None, status: str | None = None, increment_retry: bool = False) -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        shard = state.worker_shards.get(worker_id) or WorkerShard(worker_id=worker_id)
        if task_packet is not None:
            shard.current_task_packet = task_packet
        if latest_output is not None:
            shard.latest_output = latest_output
        if result_summary is not None:
            shard.result_summary = _clean_inline(result_summary, limit=180)
        if validation_feedback is not None:
            shard.validation_feedback = validation_feedback
        if status is not None:
            shard.status = status
        if increment_retry:
            shard.retry_count += 1
        state.worker_shards[worker_id] = shard
        return state

    return store.update(session_id, updater)


def append_artifact(session_id: str, *, owner: str, kind: str, content: str, linked_checklist_item: str = "") -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        state.shared_artifacts.append(
            TaskArtifact(
                artifact_id=str(uuid.uuid4()),
                owner=owner,
                kind=kind,
                content=content,
                linked_checklist_item=linked_checklist_item,
            )
        )
        return state

    return store.update(session_id, updater)


def set_final_summary(session_id: str, summary: str, *, status: str = "completed") -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        state.final_answer_summary = _clean_inline(summary, limit=240)
        state.last_run_status = status
        return state

    return store.update(session_id, updater)


def parse_validation_report(content: str | None, *, status: str = "completed") -> ValidationReport:
    raw_text = str(content or "").strip()
    if not raw_text:
        gate = "failed" if status in {"failed", "timed_out"} else "unknown"
        return ValidationReport(pass_gate=gate, summary="", raw_text=raw_text)

    gate = "unknown"
    summary = _clean_inline(raw_text, limit=220)
    rework_targets: list[ValidationFinding] = []

    lower = raw_text.lower()
    for line in raw_text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("pass_gate:"):
            candidate = lowered.split(":", 1)[1].strip()
            if candidate in {"passed", "fixes_required", "failed"}:
                gate = candidate
        elif lowered.startswith("summary:"):
            summary = stripped.split(":", 1)[1].strip() or summary
        elif stripped.startswith("- ") and ":" in stripped:
            owner, issue = stripped[2:].split(":", 1)
            owner = owner.strip()
            issue = issue.strip()
            if owner and issue:
                rework_targets.append(ValidationFinding(owner=owner, summary=_clean_inline(issue, limit=180)))

    if gate == "unknown":
        if "acceptable with fixes" in lower or "fixes_required" in lower:
            gate = "fixes_required"
        elif "should be rejected" in lower or "not acceptable" in lower:
            gate = "failed"
        elif "acceptable as-is" in lower or "pass_gate: passed" in lower:
            gate = "passed"
        elif status in {"failed", "timed_out"}:
            gate = "failed"

    return ValidationReport(pass_gate=gate, summary=summary, rework_targets=rework_targets, raw_text=raw_text)


def set_validation_report(session_id: str, report: ValidationReport) -> OrcSessionState:
    store = get_session_store()

    def updater(state: OrcSessionState) -> OrcSessionState:
        state.latest_validation_report = report
        return state

    return store.update(session_id, updater)


async def emit_checklist_sync(state: OrcSessionState) -> None:
    await emit_event(
        {
            "type": "checklist_sync",
            "task_type": state.task_type,
            "last_run_status": state.last_run_status,
            "selected_workers": state.selected_workers,
            "checklist": [item.model_dump() for item in state.execution_checklist],
        }
    )
