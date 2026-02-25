from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions


def test_daily_time_capture_dry_run_has_no_external_writes(tmp_path: Path, runner_factory) -> None:
    runner, _ = runner_factory("dry-home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    file_path = workspace / "MAT-123-note.docx"
    file_path.write_text("metadata only", encoding="utf-8")

    ts = datetime(2026, 2, 20, 12, 0, tzinfo=UTC).timestamp()
    file_path.touch()
    file_path.chmod(0o644)
    import os

    os.utime(file_path, (ts, ts))

    playbook = load_playbook(
        Path(__file__).resolve().parents[1]
        / "matteros"
        / "playbooks"
        / "daily_time_capture.yml"
    )

    output_csv = tmp_path / "dry_entries.csv"
    summary = runner.run(
        playbook=playbook,
        inputs={
            "date": "2026-02-20",
            "workspace_path": str(workspace),
            "fixtures_root": str(Path(__file__).resolve().parent / "fixtures" / "ms_graph"),
            "output_csv_path": str(output_csv),
            "matter_hint": "",
        },
        options=RunnerOptions(dry_run=True, approve_mode=False, reviewer="tester"),
    )

    assert summary.status.value == "completed"
    assert not output_csv.exists()

    apply_result = summary.outputs.get("apply_time_entries")
    assert isinstance(apply_result, dict)
    assert apply_result.get("status") == "dry_run"

    suggestions = summary.outputs.get("time_entry_suggestions")
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0
