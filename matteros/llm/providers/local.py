from __future__ import annotations

from typing import Any

from matteros.llm.tasks import get_registry


class LocalProvider:
    name = "local"
    model_name = "local-heuristic"

    def generate(self, *, task: str, payload: dict[str, Any], schema_name: str | None) -> Any:
        spec = get_registry().get(task)  # raises KeyError if unknown
        if spec.local_fallback is None:
            raise ValueError(f"task '{task}' has no local fallback")
        return spec.local_fallback(payload)
