"""Tests for the database migration framework."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from matteros.core.migrations.runner import apply_pending, get_current_version
from matteros.core.store import SQLiteStore


def test_migrations_applied_on_store_init(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    version = get_current_version(conn)
    conn.close()
    assert version >= 1


def test_schema_version_table_created(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    conn.close()
    assert tables is not None


def test_v002_creates_patterns_table(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "patterns" in tables
    assert "drafts" in tables
    assert "feedback_log" in tables


def test_v003_creates_users_table(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    version = get_current_version(conn)
    conn.close()
    assert "users" in tables
    assert version >= 3


def test_v003_adds_user_id_columns_with_default(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    try:
        for table in ("runs", "steps", "approvals", "drafts"):
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            by_name = {row[1]: row for row in rows}
            assert "user_id" in by_name, f"{table} missing user_id"
            default_value = str(by_name["user_id"][4] or "")
            assert "solo" in default_value
    finally:
        conn.close()


def test_idempotent_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    store1 = SQLiteStore(db_path)
    conn1 = store1._connect()
    v1 = get_current_version(conn1)
    conn1.close()

    store2 = SQLiteStore(db_path)
    conn2 = store2._connect()
    v2 = get_current_version(conn2)
    conn2.close()

    assert v1 == v2


def test_foreign_keys_are_enforced_on_connections(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    conn = store._connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO steps (run_id, step_id, step_type, status, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("missing-run-id", "collect_x", "collect", "running", "2026-02-25T00:00:00Z"),
            )
            conn.commit()
    finally:
        conn.close()
