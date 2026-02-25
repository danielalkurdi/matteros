from __future__ import annotations

from pathlib import Path

import pytest

from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions


def test_policy_blocks_write_without_approve(tmp_path: Path, runner_factory) -> None:
    playbook_path = tmp_path / "apply_only.yml"
    playbook_path.write_text(
        """
metadata:
  name: apply-only
  description: write test
  version: "1.0"
connectors:
  - csv_export
steps:
  - id: apply_entries
    type: apply
    config:
      connector: csv_export
      operation: export_time_entries
      source: approved_entries
      params:
        output_path: "{{inputs.output_csv_path}}"
      output: apply_result
""",
        encoding="utf-8",
    )

    playbook = load_playbook(playbook_path)
    runner, _ = runner_factory()

    with pytest.raises(Exception):
        runner.run(
            playbook=playbook,
            inputs={
                "output_csv_path": str(tmp_path / "forbidden.csv"),
                "approved_entries": [],
            },
            options=RunnerOptions(dry_run=False, approve_mode=False, reviewer="tester"),
        )
