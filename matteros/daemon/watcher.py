"""File system watcher with debounced activity detection."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class ActivityWatcher:
    """Polls watched paths for mtime changes and fires a debounced callback.

    Uses basic ``os.stat`` polling (every *poll_seconds*) instead of a
    third-party file-system notification library to avoid extra dependencies.
    Detected changes are collected into a window of *debounce_seconds* and
    delivered as a batch to *callback*.
    """

    def __init__(
        self,
        watch_paths: list[Path],
        debounce_seconds: int = 300,
        callback: Callable[[list[Path]], None] | None = None,
        poll_seconds: int = 30,
    ) -> None:
        self._watch_paths = watch_paths
        self._debounce_seconds = debounce_seconds
        self._callback = callback
        self._poll_seconds = poll_seconds

        self._running = False
        self._poll_task: asyncio.Task[None] | None = None
        self._flush_task: asyncio.Task[None] | None = None

        # path -> last known mtime
        self._mtimes: dict[Path, float] = {}
        # accumulated changes in the current debounce window
        self._pending: list[Path] = []

    async def start(self) -> None:
        """Begin polling and debounce delivery."""
        if self._running:
            return
        self._running = True
        self._mtimes = self._snapshot()
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Cancel polling and flush any remaining changes."""
        self._running = False
        for task in (self._poll_task, self._flush_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # Deliver any leftovers.
        self._flush()

    def _snapshot(self) -> dict[Path, float]:
        """Walk watched paths and record mtimes for all regular files."""
        result: dict[Path, float] = {}
        for root in self._watch_paths:
            if not root.exists():
                continue
            if root.is_file():
                try:
                    result[root] = os.stat(root).st_mtime
                except OSError:
                    pass
                continue
            for dirpath, _dirnames, filenames in os.walk(root):
                for fname in filenames:
                    fpath = Path(dirpath) / fname
                    try:
                        result[fpath] = os.stat(fpath).st_mtime
                    except OSError:
                        pass
        return result

    async def _poll_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._poll_seconds)
            try:
                current = self._snapshot()
            except Exception:
                logger.exception("watcher poll error")
                continue

            changed: list[Path] = []
            for path, mtime in current.items():
                prev = self._mtimes.get(path)
                if prev is None or mtime > prev:
                    changed.append(path)
            # Detect new files as well.
            self._mtimes = current

            if changed:
                self._pending.extend(changed)

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._debounce_seconds)
            self._flush()

    def _flush(self) -> None:
        if not self._pending:
            return
        batch = list(self._pending)
        self._pending.clear()
        if self._callback is not None:
            try:
                self._callback(batch)
            except Exception:
                logger.exception("watcher callback error")
