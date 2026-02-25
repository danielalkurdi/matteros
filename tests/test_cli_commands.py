"""Tests for CLI commands: drafts approve/reject, learn, digest, review."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from matteros.cli import app
from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager

runner = CliRunner()


def _setup_home(tmp_path: Path) -> Path:
    """Create a MatterOS home with scaffold dirs."""
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)
    (home / "auth").mkdir()
    (home / "audit").mkdir()
    return home


def _create_pending_draft(home: Path, matter_id: str = "MAT-100", duration: int = 30, confidence: float = 0.8) -> str:
    store = SQLiteStore(home / "matteros.db")
    manager = DraftManager(store)
    return manager.create_draft(
        run_id="test-run",
        entry={"matter_id": matter_id, "duration_minutes": duration, "confidence": confidence, "narrative": "Test work"},
    )


# -- drafts approve -----------------------------------------------------------


def test_drafts_approve(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    draft_id = _create_pending_draft(home)

    result = runner.invoke(app, ["drafts", "approve", draft_id, "--home", str(home)])
    assert result.exit_code == 0
    assert "approved" in result.output

    # Verify feedback_log row was created
    store = SQLiteStore(home / "matteros.db")
    with store.connection() as conn:
        rows = conn.execute("SELECT * FROM feedback_log WHERE draft_id = ?", (draft_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "approved"


def test_drafts_approve_not_found(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    # Ensure DB exists
    SQLiteStore(home / "matteros.db")

    result = runner.invoke(app, ["drafts", "approve", "nonexistent-id", "--home", str(home)])
    assert result.exit_code == 1
    assert "not found" in result.output


# -- drafts reject ------------------------------------------------------------


def test_drafts_reject(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    draft_id = _create_pending_draft(home)

    result = runner.invoke(app, ["drafts", "reject", draft_id, "--reason", "too short", "--home", str(home)])
    assert result.exit_code == 0
    assert "rejected" in result.output

    store = SQLiteStore(home / "matteros.db")
    with store.connection() as conn:
        rows = conn.execute("SELECT * FROM feedback_log WHERE draft_id = ?", (draft_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "rejected"
    assert rows[0]["reason"] == "too short"


def test_drafts_reject_no_reason(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    draft_id = _create_pending_draft(home)

    result = runner.invoke(app, ["drafts", "reject", draft_id, "--home", str(home)])
    assert result.exit_code == 0

    store = SQLiteStore(home / "matteros.db")
    with store.connection() as conn:
        rows = conn.execute("SELECT * FROM feedback_log WHERE draft_id = ?", (draft_id,)).fetchall()
    assert rows[0]["reason"] is None


# -- learn command ------------------------------------------------------------


def test_learn_no_flag(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    SQLiteStore(home / "matteros.db")

    result = runner.invoke(app, ["learn", "--home", str(home)])
    assert result.exit_code == 1
    assert "specify" in result.output


def test_learn_all_with_seeded_approvals(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    store = SQLiteStore(home / "matteros.db")

    # Seed parent run and approval rows
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json) "
            "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
            ("run-1", "test.yml", "completed", 0, 0, "{}"),
        )
        for i in range(3):
            entry = {"matter_id": "MAT-100", "duration_minutes": 30, "narrative": f"Reviewed compliance doc #{i}"}
            conn.execute(
                "INSERT INTO approvals (id, run_id, step_id, item_index, decision, reason, entry_json, reviewer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (f"a-{i}", "run-1", "step-1", i, "approve", None, json.dumps(entry), "tester"),
            )
        conn.commit()

    result = runner.invoke(app, ["learn", "--all", "--home", str(home)])
    assert result.exit_code == 0
    assert "learned from" in result.output
    assert "patterns" in result.output


# -- digest command -----------------------------------------------------------


def test_digest_week_empty_db(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    SQLiteStore(home / "matteros.db")

    result = runner.invoke(app, ["digest", "--period", "week", "--home", str(home)])
    assert result.exit_code == 0
    assert "0.0h" in result.output


def test_digest_day_with_approved_drafts(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    store = SQLiteStore(home / "matteros.db")
    manager = DraftManager(store)

    d1 = manager.create_draft(
        run_id="r1",
        entry={"matter_id": "MAT-100", "duration_minutes": 60},
    )
    manager.approve_draft(d1)

    d2 = manager.create_draft(
        run_id="r1",
        entry={"matter_id": "MAT-200", "duration_minutes": 30},
    )
    manager.approve_draft(d2)

    result = runner.invoke(app, ["digest", "--period", "day", "--home", str(home)])
    assert result.exit_code == 0
    assert "1.5h" in result.output


# -- review command (auto-approve path) ---------------------------------------


def test_review_auto_approve(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    _create_pending_draft(home, confidence=0.9)
    _create_pending_draft(home, matter_id="MAT-200", confidence=0.8)

    # Both drafts above threshold -> both auto-approved, no interactive prompt
    result = runner.invoke(app, ["review", "--auto-approve", "0.5", "--home", str(home)])
    assert result.exit_code == 0
    assert "auto-approved" in result.output
    assert "2 approved" in result.output


def test_review_no_pending(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    SQLiteStore(home / "matteros.db")

    result = runner.invoke(app, ["review", "--home", str(home)])
    assert result.exit_code == 0
    assert "no pending drafts" in result.output
