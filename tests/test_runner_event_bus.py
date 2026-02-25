"""Tests for runner EventBus integration and step registry."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from matteros.core.events import EventBus, EventType, RunEvent
from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions, WorkflowRunner
from matteros.core.types import ApprovalDecision, StepType


def test_runner_emits_events_to_bus(tmp_path: Path, runner_factory) -> None:
    runner, home = runner_factory("event-home")

    events_received: list[RunEvent] = []
    bus = EventBus()
    bus.subscribe(None, lambda e: events_received.append(e))
    runner.event_bus = bus

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "MAT-001-note.txt").write_text("test", encoding="utf-8")

    playbook = load_playbook(
        Path(__file__).resolve().parents[1] / "matteros" / "playbooks" / "daily_time_capture.yml"
    )
    runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(tmp_path / "out.csv"),
            "matter_hint": "",
        },
        options=RunnerOptions(dry_run=True, approve_mode=False, reviewer="tester"),
    )

    event_types = [e.event_type for e in events_received]
    assert EventType.RUN_STARTED in event_types
    assert EventType.RUN_COMPLETED in event_types
    assert EventType.STEP_STARTED in event_types
    assert EventType.STEP_COMPLETED in event_types


def test_runner_without_bus_still_works(tmp_path: Path, runner_factory) -> None:
    runner, _ = runner_factory("no-bus-home")
    assert runner.event_bus is None

    workspace = tmp_path / "ws"
    workspace.mkdir()

    playbook = load_playbook(
        Path(__file__).resolve().parents[1] / "matteros" / "playbooks" / "daily_time_capture.yml"
    )
    summary = runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(tmp_path / "out.csv"),
            "matter_hint": "",
        },
        options=RunnerOptions(dry_run=True),
    )
    assert summary.status.value == "completed"


def test_step_registry_custom_handler(runner_factory) -> None:
    runner, _ = runner_factory("registry-home")

    calls = []

    def custom_transform(self, step, context, options, manifests, run_id):
        calls.append(step.id)
        return [{"custom": True}]

    runner.register_step_handler(StepType.TRANSFORM, custom_transform)
    assert runner._step_handlers[StepType.TRANSFORM] == custom_transform


def test_runner_requires_approve_mode_for_approval_steps(tmp_path: Path, runner_factory) -> None:
    runner, _ = runner_factory("approve-mode-required")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "MAT-001-note.txt").write_text("test", encoding="utf-8")

    playbook = load_playbook(
        Path(__file__).resolve().parents[1] / "matteros" / "playbooks" / "daily_time_capture.yml"
    )
    out_csv = tmp_path / "out.csv"
    with pytest.raises(RuntimeError, match="approval step requires --approve"):
        runner.run(
            playbook=playbook,
            inputs={
                "date": "2026-02-20",
                "workspace_path": str(workspace),
                "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
                "output_csv_path": str(out_csv),
                "matter_hint": "",
            },
            options=RunnerOptions(dry_run=False, approve_mode=False, reviewer="tester"),
        )


def test_runner_non_dry_run_records_approvals_and_applies(tmp_path: Path, runner_factory) -> None:
    runner, _ = runner_factory("approve-and-apply")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "MAT-001-note.txt").write_text("test", encoding="utf-8")

    playbook = load_playbook(
        Path(__file__).resolve().parents[1] / "matteros" / "playbooks" / "daily_time_capture.yml"
    )
    out_csv = tmp_path / "out.csv"

    def approve_all(suggestion, index) -> ApprovalDecision:
        return ApprovalDecision(decision="approve")

    summary = runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(out_csv),
            "matter_hint": "",
        },
        options=RunnerOptions(
            dry_run=False,
            approve_mode=True,
            reviewer="tester",
            approval_handler=approve_all,
        ),
    )

    approved_entries = summary.outputs.get("approved_time_entries", [])
    apply_result = summary.outputs.get("apply_time_entries", {})

    assert isinstance(approved_entries, list)
    assert len(approved_entries) > 0
    assert apply_result.get("rows_written") == len(approved_entries)
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(approved_entries)

    with runner.store.connection() as conn:
        approvals = conn.execute(
            "SELECT decision FROM approvals WHERE run_id = ? ORDER BY item_index",
            (summary.run_id,),
        ).fetchall()

    assert len(approvals) == len(approved_entries)
    assert all(row[0] == "approve" for row in approvals)
