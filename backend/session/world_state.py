"""Render the current `<world_state>` snapshot for prompt injection.

Each turn the lead agent (`orc`) builds and mutates an `OrcSessionState`
that lives in `session/store.py`. Workers and lead need a markdown view of
that state, but the relevance differs by viewer:

- **lead** sees the full checklist, every worker shard, the latest
  validation report and the final-answer summary.
- **worker** (e.g. `dom`) sees only the checklist items it owns or
  depends on, one-line digests of sibling worker outputs (never their
  full text), and the global constraints.

The output is wrapped in `<world_state>...</world_state>` so that prompts
can reference it explicitly and so that lead can override conflicting
historical messages with it.
"""

from __future__ import annotations

from typing import Iterable

from session.state import ChecklistItem, OrcSessionState, WorkerShard

_WORKER_OWNERS = {"dom", "pln", "ana", "cpy", "crt"}


def _clean(text: str | None, limit: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _format_item(item: ChecklistItem) -> str:
    line = f"- [{item.status}] ({item.owner}) {item.item_id}: {item.title}"
    if item.depends_on:
        line += f"  ⇠ depends_on: {', '.join(item.depends_on)}"
    if item.result_preview:
        line += f"\n    preview: {_clean(item.result_preview, limit=140)}"
    if item.verification_status:
        line += f"\n    verify: {_clean(item.verification_status, limit=100)}"
    return line


def _items_relevant_to(items: Iterable[ChecklistItem], perspective: str) -> list[ChecklistItem]:
    """Return checklist items the given worker should see.

    Orc items (intake/final) are always shown so workers know where they
    sit in the pipeline. Otherwise we include only items owned by the
    worker, or items that the worker's items depend on, or items that
    depend on the worker's items.
    """
    items_list = list(items)
    own_ids = {item.item_id for item in items_list if item.owner == perspective}
    relevant: list[ChecklistItem] = []
    for item in items_list:
        if item.owner == "orc":
            relevant.append(item)
            continue
        if item.owner == perspective:
            relevant.append(item)
            continue
        # Items that depend on us, or that we depend on.
        if any(dep in own_ids for dep in item.depends_on):
            relevant.append(item)
            continue
        if item.item_id in {dep for own in items_list if own.owner == perspective for dep in own.depends_on}:
            relevant.append(item)
            continue
    return relevant


def _format_lead_shards(shards: dict[str, WorkerShard]) -> list[str]:
    lines = []
    for worker_id, shard in shards.items():
        summary = shard.validation_feedback or shard.result_summary or shard.latest_output
        status_chip = f"[{shard.status}]" if shard.status else ""
        line = f"- {worker_id} {status_chip}".strip()
        if summary:
            line += f": {_clean(summary, limit=200)}"
        if shard.retry_count:
            line += f" (retries={shard.retry_count})"
        lines.append(line)
    return lines


def _format_worker_view_shards(shards: dict[str, WorkerShard], perspective: str) -> list[str]:
    """For a worker view: show siblings' one-line digests, never full text."""
    lines = []
    for worker_id, shard in shards.items():
        if worker_id == perspective:
            continue
        digest = shard.result_summary or _clean(shard.latest_output, limit=120)
        if not digest:
            continue
        lines.append(f"- {worker_id}: {_clean(digest, limit=120)}")
    return lines


def render_world_state(state: OrcSessionState | None, *, perspective: str) -> str:
    """Render `<world_state>` for the given perspective ("lead" or worker id).

    Returns an empty string when there is nothing meaningful to render
    (first turn before orc has populated any state).
    """
    if state is None:
        return ""
    has_meat = bool(
        state.execution_checklist
        or state.worker_shards
        or state.final_answer_summary
        or state.task_type
        or state.selected_workers
        or state.constraints
    )
    if not has_meat:
        return ""

    sections: list[str] = []

    if state.user_goal:
        sections.append(f"Primary goal: {_clean(state.user_goal, limit=220)}")
    if state.task_type:
        sections.append(f"Task type: {state.task_type}")
    if state.selected_workers:
        sections.append(f"Selected workers: {', '.join(state.selected_workers)}")
    if state.constraints:
        sections.append("Constraints:\n" + "\n".join(f"- {_clean(c, limit=180)}" for c in state.constraints))

    # Checklist — filtered by perspective.
    if state.execution_checklist:
        if perspective == "lead":
            items_to_show = list(state.execution_checklist)
        else:
            items_to_show = _items_relevant_to(state.execution_checklist, perspective)
        if items_to_show:
            sections.append("Checklist:\n" + "\n".join(_format_item(item) for item in items_to_show))

    # Worker shards.
    if state.worker_shards:
        if perspective == "lead":
            shard_lines = _format_lead_shards(state.worker_shards)
        else:
            shard_lines = _format_worker_view_shards(state.worker_shards, perspective)
        if shard_lines:
            label = "Worker shards:" if perspective == "lead" else "Sibling worker digests (one-line, do not assume more context):"
            sections.append(label + "\n" + "\n".join(shard_lines))

    # Validation report — both views can see the gate/summary.
    if state.latest_validation_report and state.latest_validation_report.pass_gate != "unknown":
        report = state.latest_validation_report
        validation_lines = [f"- pass_gate: {report.pass_gate}"]
        if report.summary:
            validation_lines.append(f"- summary: {_clean(report.summary, limit=200)}")
        if perspective == "lead":
            for target in report.rework_targets:
                validation_lines.append(f"- rework {target.owner}: {_clean(target.summary, limit=160)}")
        else:
            for target in report.rework_targets:
                if target.owner == perspective:
                    validation_lines.append(f"- rework for you: {_clean(target.summary, limit=160)}")
        sections.append("Latest validation:\n" + "\n".join(validation_lines))

    # Final answer summary — lead only (worker doesn't need to know the last user-facing answer).
    if perspective == "lead" and state.final_answer_summary:
        sections.append(f"Last final summary: {_clean(state.final_answer_summary, limit=240)}")

    if not sections:
        return ""

    header = (
        "This block reflects the current session's working state. Treat it as "
        "the canonical source of truth — if it conflicts with conversation "
        "history, prefer this block."
    )
    body = "\n\n".join(sections)
    return f"<world_state perspective=\"{perspective}\">\n{header}\n\n{body}\n</world_state>"
