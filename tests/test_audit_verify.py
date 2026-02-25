from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from matteros.cli import app
from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions


def _run_sample_workflow(tmp_path: Path, runner_factory):
    runner, home = runner_factory("audit-verify-home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    file_path = workspace / "MAT-999-audit-note.txt"
    file_path.write_text("metadata only", encoding="utf-8")

    ts = datetime(2026, 2, 20, 12, 0, tzinfo=UTC).timestamp()
    os.utime(file_path, (ts, ts))

    playbook = load_playbook(
        Path(__file__).resolve().parents[1]
        / "matteros"
        / "playbooks"
        / "daily_time_capture.yml"
    )

    summary = runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(tmp_path / "audit_verify.csv"),
            "matter_hint": "",
        },
        options=RunnerOptions(dry_run=True, approve_mode=False, reviewer="tester"),
    )

    return runner, home, summary


def test_verify_run_succeeds_for_db_jsonl_and_both(tmp_path: Path, runner_factory) -> None:
    runner, _, summary = _run_sample_workflow(tmp_path, runner_factory)

    db_result = runner.audit.verify_run(run_id=summary.run_id, source="db")
    assert db_result.ok
    assert db_result.checked_events > 0
    assert db_result.last_seq is not None
    assert db_result.last_event_hash

    jsonl_result = runner.audit.verify_run(run_id=summary.run_id, source="jsonl")
    assert jsonl_result.ok
    assert jsonl_result.checked_events == db_result.checked_events
    assert jsonl_result.last_seq == db_result.last_seq
    assert jsonl_result.last_event_hash == db_result.last_event_hash

    both_result = runner.audit.verify_run(run_id=summary.run_id, source="both")
    assert both_result.ok
    assert both_result.checked_events == db_result.checked_events
    assert both_result.last_seq == db_result.last_seq


def test_verify_run_detects_db_data_tamper(tmp_path: Path, runner_factory) -> None:
    runner, _, summary = _run_sample_workflow(tmp_path, runner_factory)
    events = runner.store.list_audit_events_for_run(run_id=summary.run_id)
    assert events

    tampered_seq = int(events[0]["seq"])
    with sqlite3.connect(runner.store.db_path) as conn:
        conn.execute(
            "UPDATE audit_events SET data_json = ? WHERE seq = ?",
            ('{"tampered": true}', tampered_seq),
        )

    result = runner.audit.verify_run(run_id=summary.run_id, source="db")
    assert not result.ok
    assert result.reason == "event_hash_mismatch"
    assert result.failure_seq == tampered_seq


def test_verify_run_detects_prev_hash_mismatch(tmp_path: Path, runner_factory) -> None:
    runner, _, summary = _run_sample_workflow(tmp_path, runner_factory)
    events = runner.store.list_audit_events_for_run(run_id=summary.run_id)
    assert len(events) >= 2

    tampered_seq = int(events[1]["seq"])
    with sqlite3.connect(runner.store.db_path) as conn:
        conn.execute(
            "UPDATE audit_events SET prev_hash = ? WHERE seq = ?",
            ("not-the-previous-hash", tampered_seq),
        )

    result = runner.audit.verify_run(run_id=summary.run_id, source="db")
    assert not result.ok
    assert result.reason == "prev_hash_mismatch"
    assert result.failure_seq == tampered_seq


def test_verify_run_detects_missing_event_between_db_and_jsonl(
    tmp_path: Path,
    runner_factory,
) -> None:
    runner, home, summary = _run_sample_workflow(tmp_path, runner_factory)
    jsonl_path = home / "audit" / "events.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()

    run_line_indexes = [
        index
        for index, line in enumerate(lines)
        if json.loads(line).get("run_id") == summary.run_id
    ]
    assert run_line_indexes

    removed_index = run_line_indexes[-1]
    removed_event = json.loads(lines[removed_index])
    removed_seq = int(removed_event["seq"])

    updated_lines = [
        line for index, line in enumerate(lines) if index != removed_index
    ]
    jsonl_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    result = runner.audit.verify_run(run_id=summary.run_id, source="both")
    assert not result.ok
    assert result.reason == "missing_event"
    assert result.failure_seq == removed_seq


def test_verify_run_missing_run_returns_missing_event(tmp_path: Path, runner_factory) -> None:
    runner, _, _ = _run_sample_workflow(tmp_path, runner_factory)
    result = runner.audit.verify_run(run_id="missing-run-id", source="db")

    assert not result.ok
    assert result.reason == "missing_event"
    assert result.checked_events == 0


def test_audit_verify_cli_success_and_failure(tmp_path: Path, runner_factory) -> None:
    runner, home, summary = _run_sample_workflow(tmp_path, runner_factory)
    cli_runner = CliRunner()

    success = cli_runner.invoke(
        app,
        [
            "audit",
            "verify",
            "--run-id",
            summary.run_id,
            "--source",
            "both",
            "--home",
            str(home),
        ],
    )
    assert success.exit_code == 0
    assert "audit verified:" in success.output

    events = runner.store.list_audit_events_for_run(run_id=summary.run_id)
    tampered_seq = int(events[0]["seq"])
    with sqlite3.connect(runner.store.db_path) as conn:
        conn.execute(
            "UPDATE audit_events SET data_json = ? WHERE seq = ?",
            ('{"tampered": true}', tampered_seq),
        )

    failure = cli_runner.invoke(
        app,
        [
            "audit",
            "verify",
            "--run-id",
            summary.run_id,
            "--source",
            "db",
            "--home",
            str(home),
        ],
    )
    assert failure.exit_code == 1
    assert "reason=event_hash_mismatch" in failure.output


def test_audit_verify_cli_usage_errors(tmp_path: Path, runner_factory) -> None:
    _, home, _ = _run_sample_workflow(tmp_path, runner_factory)
    cli_runner = CliRunner()

    invalid_source = cli_runner.invoke(
        app,
        [
            "audit",
            "verify",
            "--run-id",
            "any-run-id",
            "--source",
            "invalid",
            "--home",
            str(home),
        ],
    )
    assert invalid_source.exit_code == 2
    assert "source must be db, jsonl, or both" in invalid_source.output

    unknown_run = cli_runner.invoke(
        app,
        [
            "audit",
            "verify",
            "--run-id",
            "missing-run-id",
            "--source",
            "db",
            "--home",
            str(home),
        ],
    )
    assert unknown_run.exit_code == 2
    assert "reason=missing_event" in unknown_run.output
