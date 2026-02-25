"""Tests for PatternEngine event emission."""

from __future__ import annotations

import json

from matteros.core.events import EventBus, EventType
from matteros.core.store import SQLiteStore
from matteros.learning.patterns import PatternEngine


def _seed_approvals(store, run_id="run-1"):
    """Insert some approval records so learn_from_approvals has data."""
    with store.connection() as conn:
        # We need a run first
        conn.execute(
            "INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, "test", "completed", "2024-01-01T00:00:00Z", 0, 1, "{}"),
        )
        for i in range(3):
            conn.execute(
                "INSERT INTO approvals (id, run_id, step_id, item_index, decision, reason, reviewer, created_at, resolved_at, entry_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"appr-{i}",
                    run_id,
                    "step-1",
                    i,
                    "approve",
                    "good",
                    "tester",
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                    json.dumps({
                        "matter_id": "MAT-100",
                        "duration_minutes": 30,
                        "narrative": f"Review contract clause {i}",
                        "confidence": 0.8,
                        "evidence_refs": [],
                    }),
                ),
            )
        conn.commit()


def test_pattern_learned_event_emitted(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    bus = EventBus()
    received = []
    bus.subscribe(EventType.PATTERN_LEARNED, lambda e: received.append(e))

    _seed_approvals(store)
    engine = PatternEngine(store, event_bus=bus)
    patterns = engine.learn_from_approvals("run-1")

    # Should have learned at least one pattern and emitted events
    assert len(patterns) > 0
    assert len(received) > 0
    assert all(e.event_type == EventType.PATTERN_LEARNED for e in received)


def test_pattern_learned_no_event_bus(tmp_path):
    """PatternEngine without event_bus should not raise."""
    store = SQLiteStore(tmp_path / "test.db")
    _seed_approvals(store)
    engine = PatternEngine(store)
    patterns = engine.learn_from_approvals("run-1")
    assert len(patterns) > 0
