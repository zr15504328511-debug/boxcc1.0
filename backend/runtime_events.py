from __future__ import annotations

import contextvars
import time
from collections.abc import Awaitable, Callable
from typing import Any

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]

_event_emitter_var: contextvars.ContextVar[EventEmitter | None] = contextvars.ContextVar('event_emitter', default=None)
_event_started_at_var: contextvars.ContextVar[float | None] = contextvars.ContextVar('event_started_at', default=None)
_event_message_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('event_message_id', default=None)
_event_session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('event_session_id', default=None)
_event_turn_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('event_turn_id', default=None)


def set_event_emitter(
    emitter: EventEmitter | None,
    *,
    message_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token]:
    started_at = time.perf_counter() if emitter is not None else None
    return (
        _event_emitter_var.set(emitter),
        _event_started_at_var.set(started_at),
        _event_message_id_var.set(message_id),
        _event_session_id_var.set(session_id),
        _event_turn_id_var.set(turn_id),
    )


def reset_event_emitter(tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token, contextvars.Token]) -> None:
    emitter_token, started_token, message_token, session_token, turn_token = tokens
    _event_emitter_var.reset(emitter_token)
    _event_started_at_var.reset(started_token)
    _event_message_id_var.reset(message_token)
    _event_session_id_var.reset(session_token)
    _event_turn_id_var.reset(turn_token)


def current_elapsed_ms() -> int:
    started_at = _event_started_at_var.get()
    if started_at is None:
        return 0
    return max(0, int((time.perf_counter() - started_at) * 1000))


def current_message_id() -> str | None:
    return _event_message_id_var.get()


def current_session_id() -> str | None:
    return _event_session_id_var.get()


def current_turn_id() -> str | None:
    return _event_turn_id_var.get()


async def emit_event(payload: dict[str, Any]) -> None:
    emitter = _event_emitter_var.get()
    if emitter is None:
        return
    event = dict(payload)
    event.setdefault('message_id', current_message_id())
    event.setdefault('elapsed_ms', current_elapsed_ms())
    turn_id = current_turn_id()
    if turn_id is not None:
        event.setdefault('turn_id', turn_id)
    await emitter(event)


async def emit_run_step(
    *,
    step_id: str,
    phase: str,
    agent_id: str,
    status: str,
    title: str,
    summary: str = '',
    meta: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        'type': 'run_step',
        'step_id': step_id,
        'phase': phase,
        'agent_id': agent_id,
        'status': status,
        'title': title,
        'summary': summary,
    }
    if meta:
        payload['meta'] = meta
    if dedup_key is None:
        dedup_key = f'{step_id}:{status}'
    payload['dedup_key'] = dedup_key
    await emit_event(payload)
