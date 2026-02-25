"""Tests for watcher → scheduler wiring in DaemonRunner."""

from __future__ import annotations

import asyncio
from pathlib import Path

from matteros.core.store import SQLiteStore
from matteros.daemon.runner import DaemonRunner


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    SQLiteStore(home / "matteros.db")


def test_activity_callback_triggers_run_once(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    runner = DaemonRunner(home)

    # Add a fake job
    playbook_path = tmp_path / "test.yml"
    playbook_path.write_text(
        "metadata:\n  name: test\n  description: test\n  version: '1.0'\n"
        "connectors: []\ninputs: {}\nsteps: []\n"
    )
    job_id = runner.scheduler.add_job(
        playbook_path=playbook_path,
        inputs={},
        interval_seconds=9999,
    )

    run_once_called = []

    async def mock_run_once(jid):
        run_once_called.append(jid)

    runner.scheduler.run_once = mock_run_once

    async def _test():
        await runner.start()
        try:
            runner._on_activity([Path("/some/file.txt")])
            await asyncio.sleep(0.1)
        finally:
            await runner.stop()

    asyncio.run(_test())
    assert job_id in run_once_called


def test_activity_callback_no_jobs_is_noop(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    runner = DaemonRunner(home)

    async def _test():
        await runner.start()
        try:
            runner._on_activity([Path("/some/file.txt")])
            await asyncio.sleep(0.05)
        finally:
            await runner.stop()

    asyncio.run(_test())
