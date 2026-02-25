"""Tests for the LLM task registry."""

from __future__ import annotations

import pytest

from matteros.llm.tasks import TaskRegistry, TaskSpec


def _make_spec(name: str) -> TaskSpec:
    return TaskSpec(
        name=name,
        system_prompt="sys",
        user_prompt_template="{{payload}}",
        schema_name=None,
        local_fallback=None,
    )


def test_register_and_get() -> None:
    registry = TaskRegistry()
    spec = _make_spec("alpha")
    registry.register(spec)
    assert registry.get("alpha") is spec


def test_list_tasks() -> None:
    registry = TaskRegistry()
    registry.register(_make_spec("beta"))
    registry.register(_make_spec("alpha"))
    registry.register(_make_spec("gamma"))
    assert registry.list_tasks() == ["alpha", "beta", "gamma"]


def test_duplicate_registration_raises() -> None:
    registry = TaskRegistry()
    registry.register(_make_spec("dup"))
    with pytest.raises(ValueError, match="task already registered: dup"):
        registry.register(_make_spec("dup"))


def test_unknown_task_raises() -> None:
    registry = TaskRegistry()
    with pytest.raises(KeyError, match="unknown task: nonexistent"):
        registry.get("nonexistent")
