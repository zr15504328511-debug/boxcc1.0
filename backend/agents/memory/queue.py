"""Memory update queue with debounce - batches updates to avoid excessive LLM calls."""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    thread_id: str
    messages: list[Any]
    timestamp: datetime = field(default_factory=datetime.now)
    agent_name: str | None = None


class MemoryUpdateQueue:
    """Queue that debounces memory updates to batch multiple conversations."""

    def __init__(self, debounce_seconds: int = 30):
        self._queue: list[ConversationContext] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._debounce_seconds = debounce_seconds
        self._processing = False

    def add(self, thread_id: str, messages: list[Any], agent_name: str | None = None):
        """Add a conversation to the update queue."""
        with self._lock:
            self._queue.append(ConversationContext(
                thread_id=thread_id,
                messages=messages,
                agent_name=agent_name,
            ))
            self._reset_timer()

    def _reset_timer(self):
        """Reset the debounce timer."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce_seconds, self._process_queue)
        self._timer.daemon = True
        self._timer.start()

    def _process_queue(self):
        """Process all queued conversations for memory update."""
        with self._lock:
            if not self._queue:
                return
            items = list(self._queue)
            self._queue.clear()
            self._processing = True

        try:
            from agents.memory.updater import update_memory_from_conversation

            # Process each conversation (deduplicate by thread_id, keep latest)
            by_thread: dict[str, ConversationContext] = {}
            for item in items:
                by_thread[item.thread_id] = item

            for ctx in by_thread.values():
                logger.info(f"Processing memory update for thread {ctx.thread_id}")
                update_memory_from_conversation(
                    messages=ctx.messages,
                    thread_id=ctx.thread_id,
                    agent_name=ctx.agent_name,
                )
        except Exception:
            logger.exception("Failed to process memory update queue")
        finally:
            self._processing = False

    def flush(self):
        """Immediately process all pending items (for shutdown)."""
        if self._timer is not None:
            self._timer.cancel()
        self._process_queue()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_processing(self) -> bool:
        return self._processing


# Singleton
_queue: MemoryUpdateQueue | None = None


def get_memory_queue() -> MemoryUpdateQueue:
    global _queue
    if _queue is None:
        from config.app_config import get_app_config
        config = get_app_config()
        _queue = MemoryUpdateQueue(debounce_seconds=config.memory.debounce_seconds)
    return _queue
