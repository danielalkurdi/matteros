from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from matteros.cli import app
from matteros.core.audit import AuditLogger
from matteros.core.store import SQLiteStore

runner = CliRunner()


def _seed_audit_home(tmp_path: Path, *, run_id: str) -> tuple[Path, list[dict]]:
    home = tmp_path / "cli-audit-home"
    store = SQLiteStore(home / "matteros.db")
    audit = AuditLogger(store, home / "audit" / "events.jsonl")

    events = [
        audit.append(
            run_id=run_id,
            event_type="test.start",
            actor="tester",
            step_id="s1",
            data={"index": 0},
        ),
        audit.append(
            run_id=run_id,
            event_type="test.finish",
            actor="tester",
            step_id="s2",
            data={"index": 1},
        ),
    ]
    return home, events


def test_cli_audit_verify_success(tmp_path: Path) -> None:
    run_id = "cli-success"
    home, _ = _seed_audit_home(tmp_path, run_id=run_id)

    result = runner.invoke(
        app,
        ["audit", "verify", "--run-id", run_id, "--home", str(home)],
    )

    assert result.exit_code == 0
    assert "audit verified:" in result.stdout
    assert f"run={run_id}" in result.stdout


def test_cli_audit_verify_failure_on_hash_mismatch(tmp_path: Path) -> None:
    run_id = "cli-hash-mismatch"
    home, events = _seed_audit_home(tmp_path, run_id=run_id)
    tampered_seq = int(events[-1]["seq"])

    with sqlite3.connect(home / "matteros.db") as conn:
        conn.execute(
            "UPDATE audit_events SET event_hash = ? WHERE seq = ?",
            ("f" * 64, tampered_seq),
        )

    result = runner.invoke(
        app,
        ["audit", "verify", "--run-id", run_id, "--home", str(home)],
    )

    assert result.exit_code == 1
    assert "audit verification failed:" in result.stdout
    assert "reason=event_hash_mismatch" in result.stdout


def test_cli_audit_verify_unknown_run(tmp_path: Path) -> None:
    run_id = "cli-known"
    home, _ = _seed_audit_home(tmp_path, run_id=run_id)

    result = runner.invoke(
        app,
        ["audit", "verify", "--run-id", "cli-unknown", "--home", str(home)],
    )

    assert result.exit_code == 2
    assert "audit verification failed:" in result.stdout
    assert "reason=missing_event" in result.stdout
