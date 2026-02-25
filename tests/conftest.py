from __future__ import annotations

from pathlib import Path

import pytest

from matteros.connectors import create_default_registry
from matteros.core.audit import AuditLogger
from matteros.core.policy import PolicyEngine
from matteros.core.runner import WorkflowRunner
from matteros.core.store import SQLiteStore
from matteros.llm import LLMAdapter


@pytest.fixture()
def runner_factory(tmp_path: Path):
    def _make(home_name: str = "matteros-home") -> tuple[WorkflowRunner, Path]:
        home = tmp_path / home_name
        home.mkdir(parents=True, exist_ok=True)
        runner = WorkflowRunner(
            store=SQLiteStore(home / "matteros.db"),
            connectors=create_default_registry(auth_cache_path=home / "auth" / "ms_graph_token.json"),
            llm=LLMAdapter(default_provider="local"),
            audit=AuditLogger(SQLiteStore(home / "matteros.db"), home / "audit" / "events.jsonl"),
            policy=PolicyEngine(),
        )
        return runner, home

    return _make
