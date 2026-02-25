"""User management for team mode.

Roles:
- admin: full access, user management
- attorney: create/view runs, approve own entries
- reviewer: approve entries, view audit
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from matteros.core.store import SQLiteStore


VALID_ROLES = {"admin", "attorney", "reviewer"}


class UserManager:
    """Manages user accounts for team mode."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create_user(
        self,
        *,
        username: str,
        role: str,
        password_hash: str,
    ) -> str:
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role: {role}; must be one of {VALID_ROLES}")

        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, role, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, role, password_hash, now, now),
            )
            conn.commit()
        return user_id

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT id, username, role, created_at, updated_at FROM users ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_role(self, user_id: str, role: str) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role: {role}; must be one of {VALID_ROLES}")
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (role, now, user_id),
            )
            conn.commit()

    def delete_user(self, user_id: str) -> None:
        with self.store.connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

    def check_permission(self, user_id: str, action: str) -> bool:
        """Check if a user has permission for an action.

        Permission matrix:
        - admin: all actions
        - attorney: run, approve_own, view_audit, view_runs
        - reviewer: approve, view_audit, view_runs
        """
        user = self.get_user(user_id)
        if not user:
            return False

        role = user["role"]
        if role == "admin":
            return True

        attorney_actions = {"run", "approve_own", "view_audit", "view_runs", "view_drafts"}
        reviewer_actions = {"approve", "view_audit", "view_runs", "view_drafts"}

        if role == "attorney" and action in attorney_actions:
            return True
        if role == "reviewer" and action in reviewer_actions:
            return True

        return False
