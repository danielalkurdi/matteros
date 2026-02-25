"""RunService — triggers playbook runs from the web and lists available playbooks."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from matteros.core.events import EventBus
from matteros.core.factory import build_runner_with_event_bus
from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions


class RunService:
    """Triggers playbook runs in background threads and lists available playbooks."""

    def __init__(self, home: Path, playbook_dir: Path | None = None) -> None:
        self._home = home
        self._playbook_dir = playbook_dir or home / ".." / "playbooks"

    def list_playbooks(self) -> list[dict[str, Any]]:
        """Return metadata for all YAML playbooks found in the playbook directory."""
        results: list[dict[str, Any]] = []
        search_dirs = [self._playbook_dir]

        # Also search standard locations
        project_playbooks = Path("playbooks")
        if project_playbooks.is_dir():
            search_dirs.append(project_playbooks)

        seen: set[str] = set()
        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for path in sorted(search_dir.glob("*.yml")):
                name = path.stem
                if name in seen:
                    continue
                seen.add(name)
                try:
                    pb = load_playbook(path)
                    results.append({
                        "name": pb.metadata.name,
                        "description": pb.metadata.description,
                        "version": pb.metadata.version,
                        "path": str(path),
                    })
                except Exception:
                    pass
        return results

    def trigger_run(
        self,
        *,
        playbook_name: str,
        inputs: dict[str, Any] | None = None,
        dry_run: bool = True,
        event_bus: EventBus | None = None,
    ) -> str:
        """Start a playbook run in a background thread. Returns the run_id."""
        # Find the playbook file
        playbook_path = self._find_playbook(playbook_name)
        if playbook_path is None:
            raise ValueError(f"unknown playbook: {playbook_name}")

        run_id = uuid.uuid4().hex[:12]
        thread = threading.Thread(
            target=self._run_in_thread,
            args=(playbook_path, inputs or {}, dry_run, event_bus),
            daemon=True,
            name=f"run-{run_id}",
        )
        thread.start()
        return run_id

    def _find_playbook(self, name: str) -> Path | None:
        for pb in self.list_playbooks():
            if pb["name"] == name:
                return Path(pb["path"])
        return None

    def _run_in_thread(
        self,
        playbook_path: Path,
        inputs: dict[str, Any],
        dry_run: bool,
        event_bus: EventBus | None,
    ) -> None:
        try:
            runner = build_runner_with_event_bus(self._home, event_bus)
            playbook = load_playbook(playbook_path)
            options = RunnerOptions(dry_run=dry_run)
            runner.run(playbook=playbook, inputs=inputs, options=options)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("web run failed")
