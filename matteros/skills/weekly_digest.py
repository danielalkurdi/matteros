from __future__ import annotations

from collections import defaultdict
from typing import Any


def weekly_digest(payload: dict[str, Any]) -> dict[str, Any]:
    """Local heuristic that groups time entries by matter and produces a markdown table."""
    entries = payload.get("entries", [])

    if not entries:
        return {"markdown": "| Matter | Total Minutes | Entry Count |\n|--------|---------------|-------------|\n"}

    by_matter: dict[str, dict[str, int]] = defaultdict(lambda: {"minutes": 0, "count": 0})
    for entry in entries:
        matter_id = str(entry.get("matter_id", "UNASSIGNED"))
        duration = int(entry.get("duration_minutes", 0))
        by_matter[matter_id]["minutes"] += duration
        by_matter[matter_id]["count"] += 1

    lines = ["| Matter | Total Minutes | Entry Count |", "|--------|---------------|-------------|"]
    for matter_id in sorted(by_matter):
        stats = by_matter[matter_id]
        lines.append(f"| {matter_id} | {stats['minutes']} | {stats['count']} |")

    return {"markdown": "\n".join(lines) + "\n"}
