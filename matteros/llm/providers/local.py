from __future__ import annotations

from typing import Any

from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1
from matteros.skills.draft_time_entries import draft_time_entries_from_clusters


class LocalProvider:
    name = "local"
    model_name = "local-heuristic"

    def generate(self, *, task: str, payload: dict[str, Any], schema_name: str | None) -> Any:
        if task == "draft_time_entries":
            clusters = payload.get("clusters", [])
            if not isinstance(clusters, list):
                raise ValueError("draft_time_entries requires payload['clusters'] as list")
            return {
                "schema_version": schema_name or SCHEMA_TIME_ENTRY_V1,
                "suggestions": draft_time_entries_from_clusters(clusters),
            }

        raise ValueError(f"unsupported local task: {task}")
