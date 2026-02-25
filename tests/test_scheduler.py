"""Tests for the daemon/scheduler module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from matteros.daemon.scheduler import PlaybookScheduler


@pytest.fixture()
def scheduler(tmp_path: Path) -> PlaybookScheduler:
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)
    return PlaybookScheduler(home)


# -- add / remove / list jobs -------------------------------------------------


def test_add_job(scheduler: PlaybookScheduler, tmp_path: Path) -> None:
    jid = scheduler.add_job(
        playbook_path=tmp_path / "test.yml",
        inputs={"key": "value"},
        interval_seconds=600,
    )
    assert jid
    jobs = scheduler.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == jid
    assert jobs[0]["interval"] == 600


def test_add_job_custom_id(scheduler: PlaybookScheduler, tmp_path: Path) -> None:
    jid = scheduler.add_job(
        playbook_path=tmp_path / "test.yml",
        inputs={},
        interval_seconds=300,
        job_id="my-job",
    )
    assert jid == "my-job"


def test_add_job_negative_interval_defaults(scheduler: PlaybookScheduler, tmp_path: Path) -> None:
    scheduler.add_job(
        playbook_path=tmp_path / "test.yml",
        inputs={},
        interval_seconds=-1,
    )
    jobs = scheduler.list_jobs()
    assert jobs[0]["interval"] == 1800  # default


def test_remove_job(scheduler: PlaybookScheduler, tmp_path: Path) -> None:
    jid = scheduler.add_job(
        playbook_path=tmp_path / "test.yml",
        inputs={},
        interval_seconds=300,
    )
    assert len(scheduler.list_jobs()) == 1
    scheduler.remove_job(jid)
    assert len(scheduler.list_jobs()) == 0


def test_remove_nonexistent_job(scheduler: PlaybookScheduler) -> None:
    # Should not raise
    scheduler.remove_job("does-not-exist")


def test_list_jobs_empty(scheduler: PlaybookScheduler) -> None:
    assert scheduler.list_jobs() == []


# -- persistence round-trip ---------------------------------------------------


def test_persist_and_reload(tmp_path: Path) -> None:
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)

    s1 = PlaybookScheduler(home)
    s1.add_job(
        playbook_path=tmp_path / "pb.yml",
        inputs={"x": 1},
        interval_seconds=900,
        job_id="j1",
    )

    # Create a new scheduler from the same home — should load j1
    s2 = PlaybookScheduler(home)
    jobs = s2.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "j1"
    assert jobs[0]["interval"] == 900


def test_load_corrupted_json(tmp_path: Path) -> None:
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)
    jobs_path = home / "daemon" / "jobs.json"
    jobs_path.parent.mkdir(parents=True)
    jobs_path.write_text("not valid json!!!", encoding="utf-8")

    # Should not crash
    s = PlaybookScheduler(home)
    assert s.list_jobs() == []


def test_load_missing_file(tmp_path: Path) -> None:
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)
    s = PlaybookScheduler(home)
    assert s.list_jobs() == []


# -- run_once -----------------------------------------------------------------


def test_run_once_unknown_job(scheduler: PlaybookScheduler) -> None:
    with pytest.raises(KeyError, match="unknown job"):
        asyncio.run(scheduler.run_once("nonexistent"))


# -- start / stop lifecycle ---------------------------------------------------


def test_start_stop_lifecycle(tmp_path: Path) -> None:
    home = tmp_path / "matteros-home"
    home.mkdir(parents=True)
    s = PlaybookScheduler(home)

    async def _lifecycle() -> None:
        await s.start()
        assert s._running is True
        await s.stop()
        assert s._running is False

    asyncio.run(_lifecycle())
