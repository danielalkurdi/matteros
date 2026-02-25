"""Tests for the team/reports module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from matteros.core.store import SQLiteStore
from matteros.team.reports import TeamReports


def _make_reports(tmp_path: Path) -> tuple[TeamReports, SQLiteStore]:
    store = SQLiteStore(tmp_path / "test.db")
    return TeamReports(store), store


def _ensure_run(store: SQLiteStore, run_id: str = "run-1") -> None:
    """Insert a parent run row if it doesn't already exist."""
    with store.connection() as conn:
        existing = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
                (run_id, "test.yml", "completed", 0, 0, "{}"),
            )
            conn.commit()


def _seed_approval(
    store: SQLiteStore,
    *,
    approval_id: str,
    run_id: str = "run-1",
    decision: str = "approve",
    matter_id: str = "MAT-100",
    duration_minutes: int = 30,
    reviewer: str = "alice",
) -> None:
    _ensure_run(store, run_id)
    entry = {"matter_id": matter_id, "duration_minutes": duration_minutes}
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO approvals (id, run_id, step_id, item_index, decision, reason, entry_json, reviewer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (approval_id, run_id, "step-1", 0, decision, None, json.dumps(entry), reviewer),
        )
        conn.commit()


def _seed_run(
    store: SQLiteStore,
    *,
    run_id: str,
    status: str = "completed",
    started_at: str | None = None,
) -> None:
    ts = started_at or datetime.now(UTC).isoformat()
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, playbook_name, status, started_at, ended_at, dry_run, approve_mode, input_json, output_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, "test.yml", status, ts, ts, 0, 0, "{}", "{}"),
        )
        conn.commit()


# -- hours_by_matter ----------------------------------------------------------


def test_hours_by_matter(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    _seed_approval(store, approval_id="a1", matter_id="MAT-100", duration_minutes=60)
    _seed_approval(store, approval_id="a2", matter_id="MAT-100", duration_minutes=30)
    _seed_approval(store, approval_id="a3", matter_id="MAT-200", duration_minutes=45)

    result = reports.hours_by_matter()
    assert len(result) == 2
    # Sorted by total desc
    assert result[0]["matter_id"] == "MAT-100"
    assert result[0]["total_minutes"] == 90
    assert result[0]["total_hours"] == 1.5
    assert result[1]["matter_id"] == "MAT-200"


def test_hours_by_matter_with_user_filter(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    _seed_approval(store, approval_id="a1", matter_id="MAT-100", duration_minutes=60, reviewer="alice")
    _seed_approval(store, approval_id="a2", matter_id="MAT-100", duration_minutes=30, reviewer="bob")

    result = reports.hours_by_matter(user_id="alice")
    assert len(result) == 1
    assert result[0]["total_minutes"] == 60


def test_hours_by_matter_empty(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    assert reports.hours_by_matter() == []


# -- hours_by_attorney --------------------------------------------------------


def test_hours_by_attorney(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    _seed_approval(store, approval_id="a1", reviewer="alice", duration_minutes=60)
    _seed_approval(store, approval_id="a2", reviewer="alice", duration_minutes=30)
    _seed_approval(store, approval_id="a3", reviewer="bob", duration_minutes=45)

    result = reports.hours_by_attorney()
    assert len(result) == 2
    assert result[0]["attorney"] == "alice"
    assert result[0]["total_minutes"] == 90


# -- approval_queue_depth -----------------------------------------------------


def test_approval_queue_depth(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    _seed_approval(store, approval_id="a1", decision="approve")
    _seed_approval(store, approval_id="a2", decision="approve")
    _seed_approval(store, approval_id="a3", decision="reject")

    result = reports.approval_queue_depth()
    assert result["approve"] == 2
    assert result["reject"] == 1


def test_approval_queue_depth_empty(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    assert reports.approval_queue_depth() == {}


# -- weekly_summary -----------------------------------------------------------


def test_weekly_summary(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    _seed_run(store, run_id="r1", status="completed", started_at="2024-06-10T10:00:00+00:00")
    _seed_run(store, run_id="r2", status="failed", started_at="2024-06-10T11:00:00+00:00")
    _seed_run(store, run_id="r3", status="completed", started_at="2024-06-17T10:00:00+00:00")

    result = reports.weekly_summary()
    assert len(result) >= 2
    # Each row should have the expected keys
    for row in result:
        assert "week" in row
        assert "run_count" in row
        assert "completed" in row
        assert "failed" in row


def test_weekly_summary_empty(tmp_path: Path) -> None:
    reports, store = _make_reports(tmp_path)
    assert reports.weekly_summary() == []
