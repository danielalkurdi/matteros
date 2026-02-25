from __future__ import annotations

import sqlite3

VERSION = 3
DESCRIPTION = "Add users table and user_id columns for team mode"


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_type: str, default: str
) -> None:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default!r}"
        )


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            role TEXT,
            password_hash TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    _add_column_if_missing(conn, "runs", "user_id", "TEXT", "solo")
    _add_column_if_missing(conn, "steps", "user_id", "TEXT", "solo")
    _add_column_if_missing(conn, "approvals", "user_id", "TEXT", "solo")
    _add_column_if_missing(conn, "drafts", "user_id", "TEXT", "solo")
