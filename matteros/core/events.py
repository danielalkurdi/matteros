"""Lightweight in-process event bus for MatterOS.

Runner, connectors, and audit emit typed RunEvent dataclasses.
TUI subscribes for live updates. Daemon subscribes for learning triggers.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    LLM_OUTPUT_VALIDATED = "llm.output.validated"
    APPROVAL_RECORDED = "approval.recorded"
    APPROVAL_SKIPPED = "approval.skipped_dry_run"
    DRAFT_CREATED = "draft.created"
    PATTERN_LEARNED = "pattern.learned"


@dataclass(slots=True, frozen=True)
class RunEvent:
    event_type: EventType
    run_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    step_id: str | None = None
    actor: str = "system"
    data: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[RunEvent], None]


class EventBus:
    """Simple synchronous publish-subscribe event bus.

    Handlers are called synchronously in registration order.
    Exceptions in handlers are logged but do not propagate.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType | None, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType | None, handler: EventHandler) -> None:
        """Subscribe to a specific event type, or None for all events."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType | None, handler: EventHandler) -> None:
        """Remove a handler. No-op if not found."""
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def emit(self, event: RunEvent) -> None:
        """Emit an event to all matching subscribers."""
        for handler in self._handlers.get(event.event_type, []):
            self._safe_call(handler, event)
        for handler in self._handlers.get(None, []):
            self._safe_call(handler, event)

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()

    def _safe_call(self, handler: EventHandler, event: RunEvent) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception("event handler %r failed for %s", handler, event.event_type)
