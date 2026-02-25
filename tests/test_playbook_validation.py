from __future__ import annotations

from pathlib import Path

import pytest

from matteros.core.playbook import PlaybookError, load_playbook


def test_playbook_validation_rejects_unknown_step_type(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text(
        """
metadata:
  name: invalid
  description: x
  version: "1.0"
steps:
  - id: bad
    type: unknown_step
    config: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(PlaybookError):
        load_playbook(path)
