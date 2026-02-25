from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    playbook_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    dry_run INTEGER NOT NULL,
                    approve_mode INTEGER NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    output_json TEXT,
                    error TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    item_index INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    reviewer TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    entry_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    step_id TEXT,
                    data_json TEXT NOT NULL,
                    prev_hash TEXT,
                    event_hash TEXT NOT NULL
                );
                """
            )

    def create_run(
        self,
        *,
        playbook_name: str,
        started_at: str,
        dry_run: bool,
        approve_mode: bool,
        input_payload: dict[str, Any],
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    playbook_name,
                    "running",
                    started_at,
                    int(dry_run),
                    int(approve_mode),
                    json.dumps(input_payload),
                ),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        ended_at: str,
        output_payload: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, ended_at = ?, output_json = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    ended_at,
                    json.dumps(output_payload) if output_payload is not None else None,
                    error,
                    run_id,
                ),
            )

    def start_step(
        self,
        *,
        run_id: str,
        step_id: str,
        step_type: str,
        started_at: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO steps (run_id, step_id, step_type, status, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, step_id, step_type, "running", started_at),
            )
            return int(cursor.lastrowid)

    def finish_step(
        self,
        step_row_id: int,
        *,
        status: str,
        ended_at: str,
        output_payload: Any,
        error: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE steps
                SET status = ?, ended_at = ?, output_json = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    ended_at,
                    json.dumps(output_payload) if output_payload is not None else None,
                    error,
                    step_row_id,
                ),
            )

    def insert_approval(
        self,
        *,
        run_id: str,
        step_id: str,
        item_index: int,
        decision: str,
        reason: str | None,
        reviewer: str,
        created_at: str,
        resolved_at: str,
        entry_payload: dict[str, Any] | None,
    ) -> str:
        approval_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, run_id, step_id, item_index, decision, reason, reviewer, created_at, resolved_at, entry_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    run_id,
                    step_id,
                    item_index,
                    decision,
                    reason,
                    reviewer,
                    created_at,
                    resolved_at,
                    json.dumps(entry_payload) if entry_payload is not None else None,
                ),
            )
        return approval_id

    def get_last_audit_hash(self, run_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT event_hash FROM audit_events WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return row["event_hash"] if row else None

    def insert_audit_event(
        self,
        *,
        run_id: str,
        timestamp: str,
        event_type: str,
        actor: str,
        step_id: str | None,
        data_json: str,
        prev_hash: str | None,
        event_hash: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_events (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash),
            )
            return int(cursor.lastrowid)

    def list_audit_events(self, *, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash
                FROM audit_events
                ORDER BY seq DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_audit_event(row) for row in rows]

    def list_audit_events_for_run(self, *, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash
                FROM audit_events
                WHERE run_id = ?
                ORDER BY seq ASC
                """,
                (run_id,),
            ).fetchall()
        return [self._row_to_audit_event(row) for row in rows]

    def export_audit_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return self.list_audit_events_for_run(run_id=run_id)

    def _row_to_audit_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "seq": row["seq"],
            "run_id": row["run_id"],
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "step_id": row["step_id"],
            "data": json.loads(row["data_json"]),
            "prev_hash": row["prev_hash"],
            "event_hash": row["event_hash"],
        }
