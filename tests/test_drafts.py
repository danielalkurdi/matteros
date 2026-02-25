"""Tests for the proactive drafting system."""

from __future__ import annotations

from pathlib import Path

from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager


def test_create_and_list_drafts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    draft_id = manager.create_draft(
        run_id="test-run-1",
        entry={"matter_id": "MAT-123", "duration_minutes": 30, "narrative": "Test"},
    )
    assert draft_id

    drafts = manager.list_drafts()
    assert len(drafts) == 1
    assert drafts[0]["status"] == "pending"
    assert drafts[0]["entry"]["matter_id"] == "MAT-123"


def test_approve_draft(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    draft_id = manager.create_draft(
        run_id="r1",
        entry={"matter_id": "MAT-1", "duration_minutes": 15},
    )
    manager.approve_draft(draft_id)

    draft = manager.get_draft(draft_id)
    assert draft["status"] == "approved"


def test_reject_draft(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    draft_id = manager.create_draft(
        run_id="r1",
        entry={"matter_id": "MAT-2", "duration_minutes": 10},
    )
    manager.reject_draft(draft_id)

    draft = manager.get_draft(draft_id)
    assert draft["status"] == "rejected"


def test_pending_count(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    manager.create_draft(run_id="r1", entry={"matter_id": "A"})
    manager.create_draft(run_id="r1", entry={"matter_id": "B"})
    d3 = manager.create_draft(run_id="r1", entry={"matter_id": "C"})
    manager.approve_draft(d3)

    assert manager.pending_count() == 2


def test_list_drafts_filter_by_status(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    manager = DraftManager(store)

    d1 = manager.create_draft(run_id="r1", entry={"matter_id": "A"})
    d2 = manager.create_draft(run_id="r1", entry={"matter_id": "B"})
    manager.approve_draft(d1)

    pending = manager.list_drafts(status="pending")
    assert len(pending) == 1

    approved = manager.list_drafts(status="approved")
    assert len(approved) == 1
