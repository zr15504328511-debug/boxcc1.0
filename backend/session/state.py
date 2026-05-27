from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ChecklistStatus = Literal["pending", "running", "done", "failed"]
PassGate = Literal["passed", "fixes_required", "failed", "unknown"]


class ChecklistItem(BaseModel):
    item_id: str
    title: str
    owner: str
    status: ChecklistStatus = "pending"
    depends_on: list[str] = Field(default_factory=list)
    result_preview: str = ""
    result_ref: str = ""
    verification_status: str = ""


class WorkerShard(BaseModel):
    worker_id: str
    current_task_packet: dict = Field(default_factory=dict)
    latest_output: str = ""
    result_summary: str = ""
    validation_feedback: str = ""
    retry_count: int = 0
    last_attempt: int = 0
    status: str = "idle"
    updated_at: str = Field(default_factory=utcnow_iso)


class TaskArtifact(BaseModel):
    artifact_id: str
    owner: str
    kind: str
    content: str = ""
    linked_checklist_item: str = ""
    created_at: str = Field(default_factory=utcnow_iso)


class ValidationFinding(BaseModel):
    owner: str = ""
    summary: str = ""


class ValidationReport(BaseModel):
    pass_gate: PassGate = "unknown"
    summary: str = ""
    rework_targets: list[ValidationFinding] = Field(default_factory=list)
    raw_text: str = ""
    created_at: str = Field(default_factory=utcnow_iso)


class OrcSessionState(BaseModel):
    session_id: str
    user_goal: str = ""
    task_type: str = ""
    constraints: list[str] = Field(default_factory=list)
    execution_checklist: list[ChecklistItem] = Field(default_factory=list)
    selected_workers: list[str] = Field(default_factory=list)
    worker_shards: dict[str, WorkerShard] = Field(default_factory=dict)
    shared_artifacts: list[TaskArtifact] = Field(default_factory=list)
    latest_validation_report: ValidationReport | None = None
    final_answer_summary: str = ""
    last_run_status: str = "idle"
    created_at: str = Field(default_factory=utcnow_iso)
    updated_at: str = Field(default_factory=utcnow_iso)

    def touch(self) -> None:
        self.updated_at = utcnow_iso()
