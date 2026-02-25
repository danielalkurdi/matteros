from __future__ import annotations

import sqlite3

VERSION = 2
DESCRIPTION = "Add patterns and drafts tables for learning engine"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS patterns (
            id TEXT PRIMARY KEY,
            pattern_type TEXT,
            matter_id TEXT,
            rule_json TEXT,
            confidence REAL,
            sample_count INTEGER,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            status TEXT,
            created_at TEXT,
            updated_at TEXT,
            entry_json TEXT,
            pattern_ids_json TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback_log (
            id TEXT PRIMARY KEY,
            draft_id TEXT,
            action TEXT,
            reason TEXT,
            created_at TEXT,
            FOREIGN KEY(draft_id) REFERENCES drafts(id)
        );
        """
    )
