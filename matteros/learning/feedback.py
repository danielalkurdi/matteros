"""Track user feedback on drafts for continuous learning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from matteros.core.store import SQLiteStore


class FeedbackTracker:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def record_feedback(
        self,
        draft_id: str,
        action: str,
        reason: str | None = None,
    ) -> str:
        """Insert a feedback entry into the feedback_log table.

        Args:
            draft_id: The draft this feedback applies to.
            action: One of "approved", "rejected", "edited", "expired".
            reason: Optional human-readable reason.

        Returns:
            The generated feedback_log row id.
        """
        feedback_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as conn:
            conn.execute(
                """
                INSERT INTO feedback_log (id, draft_id, action, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (feedback_id, draft_id, action, reason, now),
            )
            conn.commit()
        return feedback_id

    def get_feedback_stats(self, matter_id: str | None = None) -> dict[str, Any]:
        """Aggregate feedback by action type.

        Args:
            matter_id: Optional filter to scope stats to a single matter.

        Returns:
            Dict with keys: total, approved, rejected, edited, approval_rate.
        """
        with self.store.connection() as conn:
            if matter_id is not None:
                rows = conn.execute(
                    """
                    SELECT fl.action, COUNT(*) as cnt
                    FROM feedback_log fl
                    JOIN drafts d ON d.id = fl.draft_id
                    WHERE json_extract(d.entry_json, '$.matter_id') = ?
                    GROUP BY fl.action
                    """,
                    (matter_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT action, COUNT(*) as cnt
                    FROM feedback_log
                    GROUP BY action
                    """,
                ).fetchall()

        counts: dict[str, int] = {}
        for row in rows:
            counts[row["action"]] = row["cnt"]

        total = sum(counts.values())
        approved = counts.get("approved", 0)
        rejected = counts.get("rejected", 0)
        edited = counts.get("edited", 0)
        approval_rate = approved / total if total > 0 else 0.0

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "edited": edited,
            "approval_rate": round(approval_rate, 4),
        }
