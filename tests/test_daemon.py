"""Tests for daemon process management."""

from __future__ import annotations

from pathlib import Path

from matteros.daemon.process import is_running, read_pid, remove_pid, write_pid


def test_write_and_read_pid(tmp_path: Path) -> None:
    pid_path = write_pid(tmp_path)
    assert pid_path.exists()

    pid = read_pid(tmp_path)
    assert pid is not None
    assert isinstance(pid, int)


def test_is_running_with_current_process(tmp_path: Path) -> None:
    write_pid(tmp_path)
    assert is_running(tmp_path) is True


def test_is_running_no_pid_file(tmp_path: Path) -> None:
    assert is_running(tmp_path) is False


def test_remove_pid(tmp_path: Path) -> None:
    write_pid(tmp_path)
    remove_pid(tmp_path)
    assert read_pid(tmp_path) is None
