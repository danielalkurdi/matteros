"""PID file management for daemon process lifecycle."""

from __future__ import annotations

import os
import signal
from pathlib import Path


def _pid_path(home: Path) -> Path:
    return home / "daemon" / "matteros.pid"


def write_pid(home: Path) -> Path:
    """Write current PID to ``{home}/daemon/matteros.pid``."""
    pid_file = _pid_path(home)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    return pid_file


def read_pid(home: Path) -> int | None:
    """Read PID from file.  Returns *None* when the file is absent or empty."""
    pid_file = _pid_path(home)
    if not pid_file.exists():
        return None
    text = pid_file.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def is_running(home: Path) -> bool:
    """Return *True* if the PID in the file belongs to a live process."""
    pid = read_pid(home)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it.
        return True
    return True


def remove_pid(home: Path) -> None:
    """Delete the PID file if it exists."""
    pid_file = _pid_path(home)
    if pid_file.exists():
        pid_file.unlink()


def ensure_not_running(home: Path) -> None:
    """Raise ``RuntimeError`` if a daemon is already running."""
    if is_running(home):
        pid = read_pid(home)
        raise RuntimeError(f"daemon already running (pid {pid})")
