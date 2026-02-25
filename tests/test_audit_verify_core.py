from __future__ import annotations

import sqlite3
from pathlib import Path

from matteros.core.audit import AuditLogger
from matteros.core.store import SQLiteStore


def _build_audit(tmp_path: Path) -> tuple[AuditLogger, Path]:
    home = tmp_path / "audit-home"
    store = SQLiteStore(home / "matteros.db")
    return AuditLogger(store, home / "audit" / "events.jsonl"), home


def _seed_chain(audit: AuditLogger, *, run_id: str, count: int = 2) -> list[dict]:
    events: list[dict] = []
    for index in range(count):
        events.append(
            audit.append(
                run_id=run_id,
                event_type="test.event",
                actor="tester",
                step_id=f"step-{index}",
                data={"index": index},
            )
        )
    return events


def test_verify_run_passes_for_untampered_chain(tmp_path: Path) -> None:
    audit, _ = _build_audit(tmp_path)
    run_id = "run-valid"
    events = _seed_chain(audit, run_id=run_id, count=3)

    result = audit.verify_run(run_id=run_id, source="both")

    assert result.ok is True
    assert result.source == "both"
    assert result.checked_events == 3
    assert result.last_seq == events[-1]["seq"]
    assert result.last_event_hash == events[-1]["event_hash"]


def test_verify_run_fails_when_event_hash_tampered(tmp_path: Path) -> None:
    audit, home = _build_audit(tmp_path)
    run_id = "run-hash-tamper"
    events = _seed_chain(audit, run_id=run_id, count=2)
    last_seq = int(events[-1]["seq"])

    with sqlite3.connect(home / "matteros.db") as conn:
        conn.execute(
            "UPDATE audit_events SET event_hash = ? WHERE seq = ?",
            ("0" * 64, last_seq),
        )

    result = audit.verify_run(run_id=run_id, source="db")

    assert result.ok is False
    assert result.source == "db"
    assert result.reason == "event_hash_mismatch"
    assert result.failure_seq == last_seq


def test_verify_run_fails_when_prev_hash_link_broken(tmp_path: Path) -> None:
    audit, home = _build_audit(tmp_path)
    run_id = "run-prev-hash"
    events = _seed_chain(audit, run_id=run_id, count=2)
    second_seq = int(events[1]["seq"])

    with sqlite3.connect(home / "matteros.db") as conn:
        conn.execute(
            "UPDATE audit_events SET prev_hash = ? WHERE seq = ?",
            ("broken-link", second_seq),
        )

    result = audit.verify_run(run_id=run_id, source="db")

    assert result.ok is False
    assert result.source == "db"
    assert result.reason == "prev_hash_mismatch"
    assert result.failure_seq == second_seq


def test_verify_run_handles_single_event_chain(tmp_path: Path) -> None:
    audit, _ = _build_audit(tmp_path)
    run_id = "run-single"
    event = audit.append(
        run_id=run_id,
        event_type="test.single",
        actor="tester",
        step_id=None,
        data={"ok": True},
    )

    result = audit.verify_run(run_id=run_id, source="both")

    assert result.ok is True
    assert result.checked_events == 1
    assert result.last_seq == event["seq"]


def test_verify_run_reports_missing_event_for_unknown_run(tmp_path: Path) -> None:
    audit, _ = _build_audit(tmp_path)

    result = audit.verify_run(run_id="run-does-not-exist", source="both")

    assert result.ok is False
    assert result.source == "db"
    assert result.reason == "missing_event"
    assert result.checked_events == 0


def test_verify_run_detects_source_mismatch_when_event_missing_in_jsonl(tmp_path: Path) -> None:
    audit, home = _build_audit(tmp_path)
    run_id = "run-source-mismatch"
    _seed_chain(audit, run_id=run_id, count=2)

    jsonl_path = home / "audit" / "events.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    jsonl_path.write_text(lines[0] + "\n", encoding="utf-8")

    result = audit.verify_run(run_id=run_id, source="both")

    assert result.ok is False
    assert result.source == "both"
    assert result.reason == "missing_event"
    assert result.failure_seq is not None
