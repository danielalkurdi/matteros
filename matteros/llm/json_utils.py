from __future__ import annotations

import json
from typing import Any

from matteros.llm.errors import LLMResponseFormatError


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = _strip_code_fence(text.strip())

    parsed = _try_parse(candidate)
    if parsed is not None:
        return parsed

    # Fallback: extract largest probable JSON object from free-form text.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = _try_parse(candidate[start : end + 1])
        if parsed is not None:
            return parsed

    raise LLMResponseFormatError("provider response did not contain a valid JSON object")


def _strip_code_fence(value: str) -> str:
    if not value.startswith("```"):
        return value

    lines = value.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        body = "\n".join(lines[1:-1])
        return body.strip()

    return value


def _try_parse(candidate: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if isinstance(decoded, dict):
        return decoded
    return None
