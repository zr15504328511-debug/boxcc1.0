from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from config.paths import get_data_dir
from session.state import ChecklistItem, OrcSessionState


_INTAKE_ITEM_ID = "orc_intake"
_VERIFY_ITEM_ID = "critic_review"
_FINAL_ITEM_ID = "orc_final"
_WORKER_ORDER = ("dom", "pln", "ana", "cpy")
_CANONICAL_IDS = {_INTAKE_ITEM_ID, _VERIFY_ITEM_ID, _FINAL_ITEM_ID}
_INTAKE_TITLE = "主席团分析问题并拆解任务"
_VERIFY_TITLE = "质检部复核关键风险与交付质量"
_FINAL_TITLE = "主席团整合验证结论并返回结果"
_VERIFY_MARKERS = ("质检", "验证", "复核")


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load_raw(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {}

    def _save_raw(self, payload: dict[str, dict]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _looks_like_legacy_checklist(self, state: OrcSessionState) -> bool:
        items = state.execution_checklist
        if not items:
            return False
        ids = [str(item.item_id) for item in items]
        if any(item_id.isdigit() for item_id in ids):
            return True
        return any(item_id not in _CANONICAL_IDS and not item_id.startswith("worker_") for item_id in ids)

    @staticmethod
    def _pick(items: list[ChecklistItem], predicate, *, last: bool = False) -> ChecklistItem | None:
        seq = reversed(items) if last else items
        for item in seq:
            if predicate(item):
                return item
        return None

    @staticmethod
    def _copy_item(source: ChecklistItem | None, *, item_id: str, title: str, owner: str, status: str, depends_on: list[str]) -> ChecklistItem:
        source = source or ChecklistItem(item_id=item_id, title=title, owner=owner)
        return ChecklistItem(
            item_id=item_id,
            title=title,
            owner=owner,
            status=status,
            depends_on=depends_on,
            result_preview=source.result_preview,
            result_ref=source.result_ref,
            verification_status=source.verification_status,
        )

    def _normalize_state(self, state: OrcSessionState) -> OrcSessionState:
        if not self._looks_like_legacy_checklist(state):
            return state

        items = list(state.execution_checklist)
        worker_ids = [worker for worker in state.selected_workers if worker in _WORKER_ORDER]
        if not worker_ids:
            worker_ids = [worker for worker in _WORKER_ORDER if any(item.owner == worker for item in items)]

        intake_src = self._pick(items, lambda item: item.item_id == _INTAKE_ITEM_ID or (item.owner == "orc" and not str(item.item_id).startswith(_FINAL_ITEM_ID)))
        final_src = self._pick(items, lambda item: item.item_id == _FINAL_ITEM_ID or (item.owner == "orc" and str(item.item_id).startswith(_FINAL_ITEM_ID)), last=True)
        if final_src is None:
            final_src = self._pick(items, lambda item: item.owner == "orc", last=True)
        verify_src = self._pick(items, lambda item: item.item_id == _VERIFY_ITEM_ID or item.owner == "crt" or any(marker in (item.title or "") for marker in _VERIFY_MARKERS))

        normalized: list[ChecklistItem] = []
        intake_status = intake_src.status if intake_src else ("done" if items else "running")
        normalized.append(
            self._copy_item(
                intake_src,
                item_id=_INTAKE_ITEM_ID,
                title=_INTAKE_TITLE,
                owner="orc",
                status=intake_status,
                depends_on=[],
            )
        )

        for worker in worker_ids:
            worker_src = self._pick(items, lambda item, worker=worker: item.owner == worker)
            normalized.append(
                self._copy_item(
                    worker_src,
                    item_id=f"worker_{worker}",
                    title=worker_src.title if worker_src and worker_src.title else worker,
                    owner=worker,
                    status=(worker_src.status if worker_src else "pending"),
                    depends_on=[_INTAKE_ITEM_ID],
                )
            )

        if worker_ids or verify_src:
            normalized.append(
                self._copy_item(
                    verify_src,
                    item_id=_VERIFY_ITEM_ID,
                    title=_VERIFY_TITLE,
                    owner="crt",
                    status=(verify_src.status if verify_src else "pending"),
                    depends_on=[f"worker_{worker}" for worker in worker_ids] or [_INTAKE_ITEM_ID],
                )
            )
            final_depends = [_VERIFY_ITEM_ID]
        else:
            final_depends = [_INTAKE_ITEM_ID]

        final_status = final_src.status if final_src else "pending"
        normalized.append(
            self._copy_item(
                final_src,
                item_id=_FINAL_ITEM_ID,
                title=_FINAL_TITLE,
                owner="orc",
                status=final_status,
                depends_on=final_depends,
            )
        )

        state.execution_checklist = normalized
        return state

    def get(self, session_id: str) -> OrcSessionState | None:
        with self._lock:
            data = self._load_raw()
            raw = data.get(session_id)
            if not raw:
                return None
            state = self._normalize_state(OrcSessionState.model_validate(raw))
            data[session_id] = state.model_dump()
            self._save_raw(data)
            return state

    def get_or_create(self, session_id: str, *, user_goal: str = "") -> OrcSessionState:
        with self._lock:
            data = self._load_raw()
            raw = data.get(session_id)
            if raw:
                state = self._normalize_state(OrcSessionState.model_validate(raw))
                if user_goal and not state.user_goal:
                    state.user_goal = user_goal
                state.touch()
                data[session_id] = state.model_dump()
                self._save_raw(data)
                return state
            state = OrcSessionState(session_id=session_id, user_goal=user_goal)
            data[session_id] = state.model_dump()
            self._save_raw(data)
            return state

    def save(self, state: OrcSessionState) -> OrcSessionState:
        with self._lock:
            data = self._load_raw()
            state = self._normalize_state(state)
            state.touch()
            data[state.session_id] = state.model_dump()
            self._save_raw(data)
            return state

    def update(self, session_id: str, updater: Callable[[OrcSessionState], OrcSessionState | None]) -> OrcSessionState:
        with self._lock:
            data = self._load_raw()
            raw = data.get(session_id)
            state = self._normalize_state(OrcSessionState.model_validate(raw)) if raw else OrcSessionState(session_id=session_id)
            next_state = self._normalize_state(updater(state) or state)
            next_state.touch()
            data[session_id] = next_state.model_dump()
            self._save_raw(data)
            return next_state


_STORE: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _STORE
    if _STORE is None:
        path = get_data_dir() / 'orc_sessions.json'
        _STORE = SessionStore(path)
    return _STORE
