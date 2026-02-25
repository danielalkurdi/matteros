"""DaemonRunner — top-level orchestrator that owns EventBus, Scheduler, and Watcher."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from matteros.core.events import EventBus
from matteros.daemon.scheduler import PlaybookScheduler
from matteros.daemon.watcher import ActivityWatcher

logger = logging.getLogger(__name__)


class DaemonRunner:
    """Owns the event bus, playbook scheduler, and activity watcher.

    When the watcher detects file changes it triggers ``scheduler.run_once``
    for every registered job, feeding live activity data into playbook runs.
    """

    def __init__(
        self,
        home: Path,
        watch_paths: list[Path] | None = None,
    ) -> None:
        self.event_bus = EventBus()
        self.scheduler = PlaybookScheduler(home, event_bus=self.event_bus)
        self.watcher = ActivityWatcher(
            watch_paths=watch_paths or [],
            callback=self._on_activity,
        )
        self._home = home

    def _on_activity(self, changed: list[Path]) -> None:
        """Watcher callback — schedule a run_once for every registered job."""
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        for job_id in list(self.scheduler._jobs):
            if loop is not None:
                loop.create_task(self.scheduler.run_once(job_id))
            else:
                logger.warning(
                    "daemon: no running event loop, skipping run_once for %s",
                    job_id,
                )

    async def start(self) -> None:
        """Start both the scheduler and the file watcher."""
        await self.scheduler.start()
        await self.watcher.start()
        logger.info("daemon: started (watch_paths=%s)", self.watcher._watch_paths)

    async def stop(self) -> None:
        """Stop watcher and scheduler, clear the event bus."""
        await self.watcher.stop()
        await self.scheduler.stop()
        self.event_bus.clear()
        logger.info("daemon: stopped")
