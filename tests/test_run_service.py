"""Tests for RunService."""

from __future__ import annotations

from pathlib import Path

from matteros.core.store import SQLiteStore
from matteros.web.run_service import RunService


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    SQLiteStore(home / "matteros.db")


def test_trigger_run_creates_run(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)

    pb_dir = tmp_path / "playbooks"
    pb_dir.mkdir()
    (pb_dir / "test_run.yml").write_text(
        "metadata:\n  name: test_run\n  description: test\n  version: '1.0'\n"
        "connectors: []\ninputs: {}\nsteps:\n- id: noop\n  type: collect\n  config: {}\n"
    )

    svc = RunService(home, playbook_dir=pb_dir)
    run_id = svc.trigger_run(playbook_name="test_run", dry_run=True)
    assert run_id
    assert isinstance(run_id, str)


def test_list_playbooks_finds_yaml(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)

    pb_dir = tmp_path / "playbooks"
    pb_dir.mkdir()
    (pb_dir / "first.yml").write_text(
        "metadata:\n  name: first\n  description: First playbook\n  version: '1.0'\n"
        "connectors: []\ninputs: {}\nsteps:\n- id: noop\n  type: collect\n  config: {}\n"
    )
    (pb_dir / "second.yml").write_text(
        "metadata:\n  name: second\n  description: Second playbook\n  version: '2.0'\n"
        "connectors: []\ninputs: {}\nsteps:\n- id: noop\n  type: collect\n  config: {}\n"
    )

    svc = RunService(home, playbook_dir=pb_dir)
    playbooks = svc.list_playbooks()
    names = [pb["name"] for pb in playbooks]
    assert "first" in names
    assert "second" in names
