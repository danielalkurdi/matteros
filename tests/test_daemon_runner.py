"""Tests for the DaemonRunner orchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path

from matteros.core.events import EventBus
from matteros.core.store import SQLiteStore
from matteros.daemon.runner import DaemonRunner


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    SQLiteStore(home / "matteros.db")


def test_start_stop_lifecycle(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    runner = DaemonRunner(home)

    assert isinstance(runner.event_bus, EventBus)

    async def _lifecycle():
        await runner.start()
        assert runner.scheduler._running
        await runner.stop()
        assert not runner.scheduler._running

    asyncio.run(_lifecycle())


def test_daemon_runner_with_watch_paths(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()

    runner = DaemonRunner(home, watch_paths=[watch_dir])
    assert runner.watcher._watch_paths == [watch_dir]

    async def _lifecycle():
        await runner.start()
        await runner.stop()

    asyncio.run(_lifecycle())


def test_daemon_runner_event_bus_shared(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    runner = DaemonRunner(home)

    assert runner.scheduler._event_bus is runner.event_bus
