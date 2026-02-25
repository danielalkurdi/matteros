"""Async scheduler for running playbooks on intervals."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from matteros.core.events import EventBus
from matteros.core.factory import build_runner
from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions
from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager

logger = logging.getLogger(__name__)


@dataclass
class _Job:
    job_id: str
    playbook_path: Path
    inputs: dict[str, Any]
    interval_seconds: int
    last_run: str | None = None
    next_run: str | None = None
    end_of_day: bool = False
    last_error: str | None = None


class PlaybookScheduler:
    """Schedule playbook executions on configurable intervals.

    Jobs are persisted to ``{home}/daemon/jobs.json`` so they survive restarts.
    Each execution invokes :class:`WorkflowRunner` in **dry-run** mode by
    default.
    """

    def __init__(self, home: Path, event_bus: EventBus | None = None) -> None:
        self._home = home
        self._event_bus = event_bus
        self._store = SQLiteStore(home / "matteros.db")
        self._draft_manager = DraftManager(self._store)
        self._jobs: dict[str, _Job] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._jobs_path = home / "daemon" / "jobs.json"
        self._load_jobs()

    # -- public API -----------------------------------------------------------

    def add_job(
        self,
        playbook_path: Path,
        inputs: dict[str, Any],
        interval_seconds: int,
        job_id: str | None = None,
        end_of_day: bool = False,
    ) -> str:
        """Register a new scheduled job.  Returns the *job_id*."""
        jid = job_id or uuid.uuid4().hex[:12]
        if interval_seconds <= 0:
            interval_seconds = 1800  # default 30 min
        job = _Job(
            job_id=jid,
            playbook_path=playbook_path,
            inputs=inputs,
            interval_seconds=interval_seconds,
            end_of_day=end_of_day,
        )
        self._jobs[jid] = job
        self._persist_jobs()
        if self._running:
            self._tasks[jid] = asyncio.create_task(self._job_loop(job))
        return jid

    def remove_job(self, job_id: str) -> None:
        """Remove a job by id."""
        self._jobs.pop(job_id, None)
        task = self._tasks.pop(job_id, None)
        if task is not None:
            task.cancel()
        self._persist_jobs()

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return a serialisable summary of all registered jobs."""
        return [
            {
                "job_id": j.job_id,
                "playbook": str(j.playbook_path),
                "interval": j.interval_seconds,
                "last_run": j.last_run,
                "next_run": j.next_run,
                "end_of_day": j.end_of_day,
                "last_error": j.last_error,
            }
            for j in self._jobs.values()
        ]

    async def start(self) -> None:
        """Launch the async scheduling loops for all registered jobs."""
        if self._running:
            return
        self._running = True
        for job in self._jobs.values():
            self._tasks[job.job_id] = asyncio.create_task(self._job_loop(job))
        self._tasks["__expiration__"] = asyncio.create_task(self._expiration_loop())

    async def stop(self) -> None:
        """Gracefully cancel all job loops."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._persist_jobs()

    async def run_once(self, job_id: str) -> None:
        """Immediately execute a single job outside the normal schedule."""
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        await self._execute_job(job)

    # -- internals ------------------------------------------------------------

    async def _job_loop(self, job: _Job) -> None:
        while self._running:
            job.next_run = _compute_next_run(job.interval_seconds, job.end_of_day)
            sleep = max(0, _seconds_until(job.next_run))
            self._persist_jobs()
            await asyncio.sleep(sleep)
            await self._execute_job(job)

    async def _execute_job(self, job: _Job) -> None:
        logger.info("scheduler: running job %s (%s)", job.job_id, job.playbook_path)
        try:
            runner = build_runner(self._home)
            if self._event_bus is not None:
                runner.event_bus = self._event_bus
            playbook_def = load_playbook(job.playbook_path)
            options = RunnerOptions(dry_run=True)
            # Run synchronously in a thread to avoid blocking the event loop.
            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(
                None,
                lambda: runner.run(playbook=playbook_def, inputs=job.inputs, options=options),
            )
            job.last_run = datetime.now(UTC).isoformat()
            job.last_error = None
            self._persist_jobs()

            # Create drafts from run suggestions.
            self._create_drafts_from_run(summary)
        except Exception as exc:
            logger.exception("scheduler: job %s failed", job.job_id)
            job.last_run = datetime.now(UTC).isoformat()
            job.last_error = str(exc)
            self._persist_jobs()

    def _create_drafts_from_run(self, summary: Any) -> None:
        """Extract time_entry_suggestions from a RunSummary and create drafts."""
        suggestions = summary.outputs.get("time_entry_suggestions", [])
        if not suggestions:
            return
        try:
            count = 0
            for entry in suggestions:
                self._draft_manager.create_draft(run_id=summary.run_id, entry=entry)
                count += 1
            logger.info("scheduler: created %d drafts from run %s", count, summary.run_id)
        except Exception:
            logger.exception("scheduler: failed to create drafts from run %s", summary.run_id)

    async def _expiration_loop(self) -> None:
        """Expire stale pending drafts every hour."""
        while self._running:
            await asyncio.sleep(3600)
            try:
                expired = self._draft_manager.expire_stale_drafts(max_age_hours=72)
                if expired:
                    logger.info("scheduler: expired %d stale drafts", expired)
            except Exception:
                logger.exception("scheduler: draft expiration failed")

    # -- persistence ----------------------------------------------------------

    def _persist_jobs(self) -> None:
        self._jobs_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "job_id": j.job_id,
                "playbook_path": str(j.playbook_path),
                "inputs": j.inputs,
                "interval_seconds": j.interval_seconds,
                "last_run": j.last_run,
                "next_run": j.next_run,
                "end_of_day": j.end_of_day,
                "last_error": j.last_error,
            }
            for j in self._jobs.values()
        ]
        # Atomic write: write to temp file then rename to avoid corruption.
        import tempfile

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self._jobs_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, str(self._jobs_path))
        except BaseException:
            # Clean up temp file on failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _load_jobs(self) -> None:
        if not self._jobs_path.exists():
            return
        try:
            payload = json.loads(self._jobs_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("scheduler: could not load jobs from %s", self._jobs_path)
            return
        if not isinstance(payload, list):
            return
        for item in payload:
            if not isinstance(item, dict):
                continue
            jid = str(item.get("job_id", ""))
            if not jid:
                continue
            self._jobs[jid] = _Job(
                job_id=jid,
                playbook_path=Path(str(item.get("playbook_path", ""))),
                inputs=item.get("inputs", {}),
                interval_seconds=int(item.get("interval_seconds", 1800)),
                last_run=item.get("last_run"),
                next_run=item.get("next_run"),
                end_of_day=bool(item.get("end_of_day", False)),
                last_error=item.get("last_error"),
            )


# -- helpers ------------------------------------------------------------------


def _compute_next_run(interval_seconds: int, end_of_day: bool) -> str:
    now = datetime.now(UTC)
    if end_of_day:
        eod = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if eod <= now:
            # Already past EOD today; schedule for tomorrow.
            from datetime import timedelta

            eod = eod + timedelta(days=1)
        return eod.isoformat()
    from datetime import timedelta

    return (now + timedelta(seconds=interval_seconds)).isoformat()


def _seconds_until(iso_ts: str) -> float:
    target = datetime.fromisoformat(iso_ts)
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return (target - datetime.now(UTC)).total_seconds()
