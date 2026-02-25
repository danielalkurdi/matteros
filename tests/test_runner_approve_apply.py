from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path

from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions
from matteros.core.types import ApprovalDecision, TimeEntrySuggestion


def test_approve_run_applies_only_approved_entries(tmp_path: Path, runner_factory) -> None:
    runner, _ = runner_factory("approve-home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    file_path = workspace / "MTR-42-research.docx"
    file_path.write_text("metadata only", encoding="utf-8")

    ts = datetime(2026, 2, 20, 15, 0, tzinfo=UTC).timestamp()
    os.utime(file_path, (ts, ts))

    playbook = load_playbook(
        Path(__file__).resolve().parents[1]
        / "matteros"
        / "playbooks"
        / "daily_time_capture.yml"
    )

    output_csv = tmp_path / "approved_entries.csv"

    def approval_handler(suggestion: TimeEntrySuggestion, index: int) -> ApprovalDecision:
        if index == 0:
            edited = suggestion.model_copy(update={"duration_minutes": suggestion.duration_minutes + 6})
            return ApprovalDecision(decision="approve", edited_entry=edited)
        return ApprovalDecision(decision="reject", reason="test reject")

    summary = runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(output_csv),
            "matter_hint": "",
        },
        options=RunnerOptions(
            dry_run=False,
            approve_mode=True,
            reviewer="tester",
            approval_handler=approval_handler,
        ),
    )

    assert summary.status.value == "completed"
    assert output_csv.exists()

    with output_csv.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert int(rows[0]["duration_minutes"]) > 0

    apply_result = summary.outputs.get("apply_time_entries")
    assert isinstance(apply_result, dict)
    assert apply_result.get("rows_written") == 1

    events = runner.store.export_audit_for_run(summary.run_id)
    approval_events = [event for event in events if event["event_type"] == "approval.recorded"]
    assert len(approval_events) >= 1
