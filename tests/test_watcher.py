"""Tests for the daemon/watcher module."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from matteros.daemon.watcher import ActivityWatcher


# -- _snapshot ----------------------------------------------------------------


def test_snapshot_with_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")

    watcher = ActivityWatcher(watch_paths=[tmp_path])
    snap = watcher._snapshot()
    assert len(snap) == 2
    assert all(isinstance(v, float) for v in snap.values())


def test_snapshot_nonexistent_dir() -> None:
    watcher = ActivityWatcher(watch_paths=[Path("/tmp/nonexistent_watcher_dir_xyz")])
    snap = watcher._snapshot()
    assert snap == {}


def test_snapshot_empty_dir(tmp_path: Path) -> None:
    watcher = ActivityWatcher(watch_paths=[tmp_path])
    snap = watcher._snapshot()
    assert snap == {}


# -- start / stop lifecycle ---------------------------------------------------


def test_start_stop_no_crash(tmp_path: Path) -> None:
    watcher = ActivityWatcher(watch_paths=[tmp_path], poll_seconds=1, debounce_seconds=1)

    async def _lifecycle() -> None:
        await watcher.start()
        assert watcher._running is True
        await watcher.stop()
        assert watcher._running is False

    asyncio.run(_lifecycle())


def test_stop_flushes_pending(tmp_path: Path) -> None:
    received: list[list[Path]] = []

    def callback(paths: list[Path]) -> None:
        received.append(paths)

    watcher = ActivityWatcher(
        watch_paths=[tmp_path],
        poll_seconds=60,
        debounce_seconds=60,
        callback=callback,
    )
    # Manually add pending items
    watcher._pending = [tmp_path / "fake.txt"]

    async def _stop() -> None:
        await watcher.stop()

    asyncio.run(_stop())
    assert len(received) == 1
    assert received[0] == [tmp_path / "fake.txt"]


# -- new file detection -------------------------------------------------------


def test_new_file_detected(tmp_path: Path) -> None:
    received: list[list[Path]] = []

    def callback(paths: list[Path]) -> None:
        received.append(paths)

    watcher = ActivityWatcher(
        watch_paths=[tmp_path],
        poll_seconds=1,
        debounce_seconds=1,
        callback=callback,
    )

    async def _detect() -> None:
        await watcher.start()
        # Create a new file after initial snapshot
        (tmp_path / "new.txt").write_text("new file")
        # Give the poll loop time to detect
        await asyncio.sleep(2.5)
        await watcher.stop()

    asyncio.run(_detect())
    # Callback should have been called with the new file
    all_paths = [p for batch in received for p in batch]
    assert any("new.txt" in str(p) for p in all_paths)


# -- callback error handling --------------------------------------------------


def test_callback_error_does_not_crash(tmp_path: Path) -> None:
    call_count = 0

    def bad_callback(paths: list[Path]) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("callback boom")

    watcher = ActivityWatcher(
        watch_paths=[tmp_path],
        poll_seconds=60,
        debounce_seconds=60,
        callback=bad_callback,
    )
    # Manually trigger flush with pending items
    watcher._pending = [tmp_path / "x.txt"]
    watcher._flush()  # should not raise
    assert call_count == 1
