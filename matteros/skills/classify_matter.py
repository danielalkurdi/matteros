from __future__ import annotations

from typing import Any

from matteros.skills.draft_time_entries import infer_matter_id


def classify_matter(payload: dict[str, Any]) -> dict[str, Any]:
    """Local heuristic that classifies texts into a matter ID with confidence."""
    texts = payload.get("texts", [])
    matter_id = infer_matter_id(texts)
    confidence = 0.9 if matter_id != "UNASSIGNED" else 0.1
    return {"matter_id": matter_id, "confidence": confidence}
