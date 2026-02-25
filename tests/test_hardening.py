"""Edge-case and hardening tests."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from matteros.core.migrations.runner import apply_pending, get_current_version
from matteros.core.store import SQLiteStore


# -- Migration idempotency ------------------------------------------------


def test_v003_idempotent_column_add(tmp_path: Path) -> None:
    """Running v003 migration twice must not crash (duplicate column)."""
    store = SQLiteStore(tmp_path / "test.db")
    # Migrations already ran once during __init__. Force-apply again.
    with store.connection() as conn:
        from matteros.core.migrations.v003_users import upgrade

        upgrade(conn)  # second run — should be a no-op
        conn.commit()

    # Verify columns still exist and are usable.
    with store.connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()]
        assert "user_id" in cols


def test_fresh_db_has_all_columns(tmp_path: Path) -> None:
    """A fresh database should have user_id columns on all tables."""
    store = SQLiteStore(tmp_path / "fresh.db")
    with store.connection() as conn:
        for table in ("runs", "steps", "approvals", "drafts"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            assert "user_id" in cols, f"{table} missing user_id column"


# -- iCal CRLF handling --------------------------------------------------


def test_ical_crlf_events(tmp_path: Path) -> None:
    """iCal connector should parse files with CRLF line endings."""
    from matteros.connectors.ical import ICalConnector

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Team Standup\r\n"
        "DTSTART:20240115T090000Z\r\n"
        "DTEND:20240115T093000Z\r\n"
        "UID:abc123\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    ics_file = tmp_path / "test.ics"
    ics_file.write_text(ics_content, encoding="utf-8")

    connector = ICalConnector()
    events = connector.read("events", {"path": str(ics_file)}, {})
    assert len(events) == 1
    assert events[0]["summary"] == "Team Standup"
    assert events[0]["uid"] == "abc123"


def test_ical_lf_events(tmp_path: Path) -> None:
    """iCal connector should also parse files with plain LF endings."""
    from matteros.connectors.ical import ICalConnector

    ics_content = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:Review Meeting\n"
        "DTSTART:20240115T140000Z\n"
        "DTEND:20240115T150000Z\n"
        "UID:def456\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    ics_file = tmp_path / "test_lf.ics"
    ics_file.write_text(ics_content, encoding="utf-8")

    connector = ICalConnector()
    events = connector.read("events", {"path": str(ics_file)}, {})
    assert len(events) == 1
    assert events[0]["summary"] == "Review Meeting"


# -- DraftManager graceful error ------------------------------------------


def test_draft_manager_missing_table(tmp_path: Path) -> None:
    """DraftManager operations should raise clear errors if drafts table is missing."""
    from matteros.drafts.manager import DraftManager

    # Create a bare database without running migrations.
    db_path = tmp_path / "bare.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS dummy (id TEXT)")
    conn.close()

    # Build a minimal store pointing at this bare DB (skip init).
    store = SQLiteStore.__new__(SQLiteStore)
    store.db_path = db_path

    dm = DraftManager(store=store)
    with pytest.raises(sqlite3.OperationalError):
        dm.list_drafts()


# -- Scheduler atomic write recovery -------------------------------------


def test_scheduler_atomic_write(tmp_path: Path) -> None:
    """Scheduler should write jobs atomically via temp-file + rename."""
    from matteros.daemon.scheduler import PlaybookScheduler

    home = tmp_path / "home"
    home.mkdir()
    sched = PlaybookScheduler(home=home)

    pb_path = tmp_path / "test.yml"
    pb_path.write_text("name: test\nsteps: []\n", encoding="utf-8")

    jid = sched.add_job(
        playbook_path=pb_path, inputs={}, interval_seconds=3600
    )

    jobs_file = home / "daemon" / "jobs.json"
    assert jobs_file.exists()
    data = json.loads(jobs_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["job_id"] == jid

    # Verify no leftover temp files.
    tmp_files = list((home / "daemon").glob("*.tmp"))
    assert tmp_files == []


def test_scheduler_last_error_field(tmp_path: Path) -> None:
    """Job state should include last_error field."""
    from matteros.daemon.scheduler import PlaybookScheduler

    home = tmp_path / "home"
    home.mkdir()
    sched = PlaybookScheduler(home=home)

    pb_path = tmp_path / "test.yml"
    pb_path.write_text("name: test\nsteps: []\n", encoding="utf-8")

    sched.add_job(playbook_path=pb_path, inputs={}, interval_seconds=3600)
    jobs = sched.list_jobs()
    assert len(jobs) == 1
    assert "last_error" in jobs[0]
    assert jobs[0]["last_error"] is None


# -- Pattern engine with empty feedback -----------------------------------


def test_pattern_engine_empty_approvals(tmp_path: Path) -> None:
    """Pattern engine should handle runs with zero approvals."""
    from matteros.learning.patterns import PatternEngine

    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store=store)

    # Create a dummy run.
    run_id = store.create_run(
        playbook_name="test",
        started_at="2024-01-01T00:00:00Z",
        dry_run=True,
        approve_mode=False,
        input_payload={},
    )
    # Learn from empty approval set — should not crash.
    patterns = engine.learn_from_approvals(run_id)
    assert patterns == []


def test_pattern_engine_apply_empty(tmp_path: Path) -> None:
    """Applying patterns with no stored patterns should return suggestions unchanged."""
    from matteros.learning.patterns import PatternEngine

    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store=store)
    suggestions = [{"matter_id": "M001", "duration_minutes": 30, "confidence": 0.5}]
    result = engine.apply_patterns(suggestions)
    assert result == suggestions


# -- Store connection context manager -------------------------------------


def test_store_connection_context_manager(tmp_path: Path) -> None:
    """The connection() context manager should auto-close the connection."""
    store = SQLiteStore(tmp_path / "test.db")
    with store.connection() as conn:
        assert conn is not None
        row = conn.execute("SELECT 1").fetchone()
        assert row[0] == 1
    # Connection should be closed after exiting the context.
    # Attempting to use it should raise.
    with pytest.raises(Exception):
        conn.execute("SELECT 1")
