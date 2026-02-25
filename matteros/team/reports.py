"""Team reporting — hours by matter, by attorney, approval queue depth."""

from __future__ import annotations

import json
from typing import Any

from matteros.core.store import SQLiteStore


class TeamReports:
    """Generate team-level reports from run and approval data."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def hours_by_matter(self, *, user_id: str | None = None) -> list[dict[str, Any]]:
        """Aggregate approved hours grouped by matter_id."""
        conn = self.store._connect()
        try:
            query = "SELECT entry_json FROM approvals WHERE decision = 'approve' AND entry_json IS NOT NULL"
            params: tuple[Any, ...] = ()
            if user_id:
                query += " AND reviewer = ?"
                params = (user_id,)
            rows = conn.execute(
                query,
                params,
            ).fetchall()
        finally:
            conn.close()

        by_matter: dict[str, float] = {}
        for row in rows:
            entry = json.loads(row["entry_json"])
            matter = entry.get("matter_id", "UNASSIGNED")
            minutes = entry.get("duration_minutes", 0)
            by_matter[matter] = by_matter.get(matter, 0) + minutes

        return [
            {"matter_id": k, "total_minutes": v, "total_hours": round(v / 60, 2)}
            for k, v in sorted(by_matter.items(), key=lambda x: -x[1])
        ]

    def hours_by_attorney(self) -> list[dict[str, Any]]:
        """Aggregate approved hours grouped by reviewer (attorney)."""
        conn = self.store._connect()
        try:
            rows = conn.execute(
                """
                SELECT reviewer, SUM(
                    CASE WHEN entry_json IS NOT NULL
                    THEN json_extract(entry_json, '$.duration_minutes')
                    ELSE 0 END
                ) as total_minutes
                FROM approvals
                WHERE decision = 'approve'
                GROUP BY reviewer
                ORDER BY total_minutes DESC
                """
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "attorney": row["reviewer"],
                "total_minutes": row["total_minutes"] or 0,
                "total_hours": round((row["total_minutes"] or 0) / 60, 2),
            }
            for row in rows
        ]

    def approval_queue_depth(self) -> dict[str, int]:
        """Count approvals by decision status."""
        conn = self.store._connect()
        try:
            rows = conn.execute(
                "SELECT decision, COUNT(*) as cnt FROM approvals GROUP BY decision"
            ).fetchall()
        finally:
            conn.close()

        return {row["decision"]: row["cnt"] for row in rows}

    def weekly_summary(self, *, weeks: int = 4) -> list[dict[str, Any]]:
        """Per-week summary of runs and approved hours."""
        conn = self.store._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    strftime('%Y-W%W', started_at) as week,
                    COUNT(*) as run_count,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM runs
                GROUP BY week
                ORDER BY week DESC
                LIMIT ?
                """,
                (weeks,),
            ).fetchall()
        finally:
            conn.close()

        return [dict(r) for r in rows]
