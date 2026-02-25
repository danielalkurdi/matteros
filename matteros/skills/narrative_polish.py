from __future__ import annotations

import re
from typing import Any


def narrative_polish(payload: dict[str, Any]) -> dict[str, Any]:
    """Local heuristic that cleans up time entry narratives."""
    text = str(payload.get("narrative", ""))

    # Remove evidence reference markers like [ref:xxx]
    text = re.sub(r"\[ref:[^\]]*\]", "", text)

    # Remove duplicate consecutive words (case-insensitive).
    # Run in a loop to catch overlapping or chained duplicates.
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

    # Capitalize first letter of each sentence
    def _capitalize_sentence(match: re.Match[str]) -> str:
        return match.group(0).upper()

    # After sentence-ending punctuation + space, capitalize next letter
    text = re.sub(r"(?<=^)(\w)", _capitalize_sentence, text)
    text = re.sub(r"(?<=[.!?]\s)(\w)", _capitalize_sentence, text)

    text = text.strip()

    return {"polished_narrative": text}
