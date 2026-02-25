from __future__ import annotations

import importlib
import pkgutil
import sqlite3
from typing import Any

from matteros.core import migrations as _migrations_pkg


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        )
        """
    )


def get_current_version(conn: sqlite3.Connection) -> int:
    _ensure_schema_version_table(conn)
    row = conn.execute(
        "SELECT MAX(version) AS v FROM schema_version"
    ).fetchone()
    return row[0] if row[0] is not None else 0


def _discover_migrations() -> list[dict[str, Any]]:
    migrations: list[dict[str, Any]] = []
    prefix = _migrations_pkg.__name__ + "."

    for importer, modname, ispkg in pkgutil.iter_modules(
        _migrations_pkg.__path__, prefix
    ):
        if ispkg:
            continue
        mod = importlib.import_module(modname)
        version = getattr(mod, "VERSION", None)
        if version is None:
            continue
        migrations.append(
            {
                "version": mod.VERSION,
                "description": mod.DESCRIPTION,
                "upgrade": mod.upgrade,
            }
        )

    migrations.sort(key=lambda m: m["version"])
    return migrations


def apply_pending(conn: sqlite3.Connection) -> list[int]:
    _ensure_schema_version_table(conn)
    current = get_current_version(conn)
    applied: list[int] = []

    for mig in _discover_migrations():
        if mig["version"] <= current:
            continue
        mig["upgrade"](conn)
        conn.execute(
            """
            INSERT INTO schema_version (version, applied_at, description)
            VALUES (?, datetime('now'), ?)
            """,
            (mig["version"], mig["description"]),
        )
        applied.append(mig["version"])

    return applied
