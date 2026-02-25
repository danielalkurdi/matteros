from __future__ import annotations

from pathlib import Path

import yaml

from matteros.core.types import PlaybookDefinition


class PlaybookError(Exception):
    """Raised when a playbook cannot be loaded or validated."""


def load_playbook(path: Path) -> PlaybookDefinition:
    if not path.exists():
        raise PlaybookError(f"playbook file not found: {path}")

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PlaybookError(f"invalid yaml in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise PlaybookError("playbook root must be a mapping")

    try:
        return PlaybookDefinition.model_validate(payload)
    except Exception as exc:  # pydantic emits rich errors already
        raise PlaybookError(f"invalid playbook schema: {exc}") from exc
