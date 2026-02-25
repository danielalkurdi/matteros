from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskSpec:
    name: str
    system_prompt: str
    user_prompt_template: str
    schema_name: str | None
    local_fallback: Callable[..., Any] | None


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskSpec] = {}

    def register(self, spec: TaskSpec) -> None:
        if spec.name in self._tasks:
            raise ValueError(f"task already registered: {spec.name}")
        self._tasks[spec.name] = spec

    def get(self, task_name: str) -> TaskSpec:
        try:
            return self._tasks[task_name]
        except KeyError:
            raise KeyError(f"unknown task: {task_name}") from None

    def list_tasks(self) -> list[str]:
        return sorted(self._tasks.keys())


# Module-level singleton
_registry = TaskRegistry()


def get_registry() -> TaskRegistry:
    return _registry


# ---------------------------------------------------------------------------
# Built-in task registrations
# ---------------------------------------------------------------------------

from matteros.skills.draft_time_entries import draft_time_entries_from_clusters  # noqa: E402
from matteros.skills.narrative_polish import narrative_polish  # noqa: E402
from matteros.skills.classify_matter import classify_matter  # noqa: E402
from matteros.skills.weekly_digest import weekly_digest  # noqa: E402


def _draft_time_entries_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrapper that extracts clusters from payload and returns the full envelope."""
    clusters = payload.get("clusters", [])
    from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1

    return {
        "schema_version": SCHEMA_TIME_ENTRY_V1,
        "suggestions": draft_time_entries_from_clusters(clusters),
    }


_registry.register(
    TaskSpec(
        name="draft_time_entries",
        system_prompt=(
            "You are a legal ops assistant. Return only valid JSON matching the provided schema."
        ),
        user_prompt_template=(
            "Generate a JSON response for task 'draft_time_entries'.\n"
            "Payload:\n{{payload}}"
        ),
        schema_name="time_entry_suggestions.v1",
        local_fallback=_draft_time_entries_fallback,
    )
)

_registry.register(
    TaskSpec(
        name="narrative_polish",
        system_prompt=(
            "You are a legal writing assistant. Polish time entry narratives for clarity, "
            "grammar, and professional tone. Return only valid JSON."
        ),
        user_prompt_template=(
            "Polish the following time entry narrative.\n"
            "Payload:\n{{payload}}"
        ),
        schema_name=None,
        local_fallback=narrative_polish,
    )
)

_registry.register(
    TaskSpec(
        name="classify_matter",
        system_prompt=(
            "You are a legal ops assistant that classifies activity text into matter IDs. "
            "Return only valid JSON."
        ),
        user_prompt_template=(
            "Classify the following texts into a matter ID.\n"
            "Payload:\n{{payload}}"
        ),
        schema_name=None,
        local_fallback=classify_matter,
    )
)

_registry.register(
    TaskSpec(
        name="weekly_digest",
        system_prompt=(
            "You are a legal ops assistant that summarises weekly time entries into a digest. "
            "Return only valid JSON with a markdown table."
        ),
        user_prompt_template=(
            "Produce a weekly digest for the following time entries.\n"
            "Payload:\n{{payload}}"
        ),
        schema_name=None,
        local_fallback=weekly_digest,
    )
)
