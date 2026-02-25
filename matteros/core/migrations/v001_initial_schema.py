from __future__ import annotations

import sqlite3

VERSION = 1
DESCRIPTION = "Initial schema: runs, steps, approvals, audit_events"


def upgrade(conn: sqlite3.Connection) -> None:
    # No-op: tables already created by store.py _init_db.
    pass
