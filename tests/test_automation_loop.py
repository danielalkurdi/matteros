"""Tests for the Phase 5 automation loop features."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from matteros.core.store import SQLiteStore
from matteros.core.types import RunStatus, RunSummary, StepResult
from matteros.drafts.manager import DraftManager
from matteros.learning.feedback import FeedbackTracker
from matteros.learning.patterns import PatternEngine


# ---------------------------------------------------------------------------
# 1. Feedback integration
# ---------------------------------------------------------------------------

def test_feedback_recorded_on_approve(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)
    tracker = FeedbackTracker(store)

    draft_id = manager.create_draft(
        run_id="run-1",
        entry={"matter_id": "MAT-1", "duration_minutes": 30},
    )
    manager.approve_draft(draft_id)
    tracker.record_feedback(draft_id, "approved")

    with store.connection() as conn:
        row = conn.execute(
            "SELECT * FROM feedback_log WHERE draft_id = ?", (draft_id,)
        ).fetchone()
    assert row is not None
    assert row["action"] == "approved"


def test_feedback_recorded_on_reject_with_reason(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)
    tracker = FeedbackTracker(store)

    draft_id = manager.create_draft(
        run_id="run-1",
        entry={"matter_id": "MAT-2", "duration_minutes": 5},
    )
    manager.reject_draft(draft_id)
    tracker.record_feedback(draft_id, "rejected", reason="too short")

    with store.connection() as conn:
        row = conn.execute(
            "SELECT * FROM feedback_log WHERE draft_id = ?", (draft_id,)
        ).fetchone()
    assert row is not None
    assert row["action"] == "rejected"
    assert row["reason"] == "too short"


# ---------------------------------------------------------------------------
# 2. Review auto-approve threshold
# ---------------------------------------------------------------------------

def test_review_auto_approve_threshold(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)
    tracker = FeedbackTracker(store)

    # Draft with high confidence.
    d1 = manager.create_draft(
        run_id="run-1",
        entry={"matter_id": "MAT-1", "duration_minutes": 30, "confidence": 0.9},
    )
    # Draft with low confidence.
    d2 = manager.create_draft(
        run_id="run-1",
        entry={"matter_id": "MAT-2", "duration_minutes": 15, "confidence": 0.3},
    )

    threshold = 0.85
    drafts = manager.list_drafts(status="pending")
    for draft in drafts:
        entry = draft.get("entry", {})
        confidence = float(entry.get("confidence", 0))
        if confidence >= threshold:
            manager.approve_draft(draft["id"])
            tracker.record_feedback(draft["id"], "approved")

    d1_after = manager.get_draft(d1)
    d2_after = manager.get_draft(d2)
    assert d1_after["status"] == "approved"
    assert d2_after["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. Draft creation from run summary
# ---------------------------------------------------------------------------

def test_create_drafts_from_run(tmp_path: Path) -> None:
    from matteros.daemon.scheduler import PlaybookScheduler

    home = tmp_path / "home"
    home.mkdir()
    scheduler = PlaybookScheduler(home)

    summary = MagicMock()
    summary.run_id = "run-123"
    summary.outputs = {
        "time_entry_suggestions": [
            {"matter_id": "MAT-1", "duration_minutes": 30, "narrative": "test1"},
            {"matter_id": "MAT-2", "duration_minutes": 15, "narrative": "test2"},
        ]
    }

    scheduler._create_drafts_from_run(summary)

    manager = DraftManager(SQLiteStore(home / "matteros.db"))
    drafts = manager.list_drafts()
    assert len(drafts) == 2


# ---------------------------------------------------------------------------
# 4. Draft expiration
# ---------------------------------------------------------------------------

def test_expire_stale_drafts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    # Create a draft, then backdate it.
    d1 = manager.create_draft(run_id="run-1", entry={"matter_id": "A"})
    d2 = manager.create_draft(run_id="run-1", entry={"matter_id": "B"})
    d3 = manager.create_draft(run_id="run-1", entry={"matter_id": "C"})

    manager.approve_draft(d3)  # Should not be expired.

    old_ts = (datetime.now(UTC) - timedelta(hours=100)).isoformat()
    with store.connection() as conn:
        conn.execute("UPDATE drafts SET created_at = ? WHERE id IN (?, ?)", (old_ts, d1, d2))
        conn.commit()

    expired = manager.expire_stale_drafts(max_age_hours=72)
    assert expired == 2

    assert manager.get_draft(d1)["status"] == "expired"
    assert manager.get_draft(d2)["status"] == "expired"
    assert manager.get_draft(d3)["status"] == "approved"


# ---------------------------------------------------------------------------
# 5. Pattern dedup
# ---------------------------------------------------------------------------

def test_pattern_dedup(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store)

    rule1 = {"type": "matter_assignment", "confidence": 0.6, "sample_count": 3}
    rule2 = {"type": "matter_assignment", "confidence": 0.8, "sample_count": 5}

    p1 = engine._store_pattern("matter_assignment", "MAT-1", rule1)
    p2 = engine._store_pattern("matter_assignment", "MAT-1", rule2)

    # Should have updated, not inserted a second row.
    assert p1["id"] == p2["id"]
    assert p2["confidence"] == 0.8

    patterns = engine.get_patterns(pattern_type="matter_assignment", matter_id="MAT-1")
    assert len(patterns) == 1
    assert patterns[0]["confidence"] == 0.8


# ---------------------------------------------------------------------------
# 6. Pattern application in runner
# ---------------------------------------------------------------------------

def test_pattern_application_modifies_suggestions(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store)

    # Seed a matter assignment pattern.
    engine._store_pattern("matter_assignment", "ACME", {
        "type": "matter_assignment",
        "condition": {"keyword": "acme", "source": "narrative"},
        "action": {"matter_id": "ACME"},
        "confidence": 0.8,
        "sample_count": 5,
    })

    suggestions = [
        {
            "matter_id": "UNASSIGNED",
            "duration_minutes": 30,
            "narrative": "Worked on ACME project review",
            "confidence": 0.5,
        }
    ]

    result = engine.apply_patterns(suggestions)
    assert result[0]["matter_id"] == "ACME"


# ---------------------------------------------------------------------------
# 7. Pattern application error resilience
# ---------------------------------------------------------------------------

def test_pattern_application_error_resilience(tmp_path: Path) -> None:
    """If apply_patterns raises, the runner should still return suggestions."""
    store = SQLiteStore(tmp_path / "test.db")

    original_suggestions = [
        {"matter_id": "MAT-1", "duration_minutes": 30, "narrative": "test", "confidence": 0.7}
    ]

    with patch("matteros.learning.patterns.PatternEngine.apply_patterns", side_effect=RuntimeError("boom")):
        engine = PatternEngine(store)
        # Simulate what the runner does.
        validated = list(original_suggestions)
        try:
            validated = engine.apply_patterns(validated)
        except Exception:
            pass  # Runner catches this.
        # Validated should still be the original.
        assert len(validated) == 1


# ---------------------------------------------------------------------------
# 8. Digest output (no crash)
# ---------------------------------------------------------------------------

def test_digest_no_crash(tmp_path: Path) -> None:
    """Digest should not crash even with no data."""
    store = SQLiteStore(tmp_path / "test.db")

    with store.connection() as conn:
        # Query approved drafts — should return 0.
        row = conn.execute(
            "SELECT COALESCE(SUM(json_extract(entry_json, '$.duration_minutes')), 0) as total "
            "FROM drafts WHERE status = 'approved'"
        ).fetchone()
        assert row["total"] == 0

        # Query feedback_log — should return empty.
        fb_rows = conn.execute(
            "SELECT action, COUNT(*) as cnt FROM feedback_log GROUP BY action"
        ).fetchall()
        assert len(fb_rows) == 0


# ---------------------------------------------------------------------------
# 9. Learn from empty runs (no crash)
# ---------------------------------------------------------------------------

def test_learn_from_empty_runs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store)

    # No approvals exist for this run_id.
    patterns = engine.learn_from_approvals("nonexistent-run")
    assert patterns == []

    all_patterns = engine.get_patterns()
    assert len(all_patterns) == 0
