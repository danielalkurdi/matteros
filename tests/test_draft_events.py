"""Tests for DraftManager event emission."""

from __future__ import annotations

from matteros.core.events import EventBus, EventType, RunEvent
from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager


def test_draft_created_event_emitted(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    bus = EventBus()
    received = []
    bus.subscribe(EventType.DRAFT_CREATED, lambda e: received.append(e))

    manager = DraftManager(store, event_bus=bus)
    draft_id = manager.create_draft(
        run_id="run-1",
        entry={"matter_id": "MAT-100", "duration_minutes": 30},
    )

    assert len(received) == 1
    assert received[0].event_type == EventType.DRAFT_CREATED
    assert received[0].data["draft_id"] == draft_id
    assert received[0].run_id == "run-1"


def test_draft_created_no_event_bus(tmp_path):
    """DraftManager without event_bus should not raise."""
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)
    draft_id = manager.create_draft(
        run_id="run-2",
        entry={"matter_id": "MAT-200", "duration_minutes": 15},
    )
    assert draft_id  # just verify it works silently
