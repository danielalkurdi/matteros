"""Tests for per-run SSE streaming."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from matteros.core.store import SQLiteStore
from matteros.web.app import create_app


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(home / "matteros.db")
    # Insert a run and some events scoped to it
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("run-sse-1", "test", "completed", "2024-01-01T00:00:00Z", 1, 0, "{}"),
        )
        conn.execute(
            "INSERT INTO audit_events (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-sse-1", "2024-01-01T00:00:01Z", "step.started", "system", "s1", "{}", None, "h1"),
        )
        conn.execute(
            "INSERT INTO audit_events (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-sse-1", "2024-01-01T00:00:02Z", "run.completed", "system", None, "{}", "h1", "h2"),
        )
        # An event for a different run should NOT appear
        conn.execute(
            "INSERT INTO audit_events (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-other", "2024-01-01T00:00:03Z", "run.started", "system", None, "{}", "h2", "h3"),
        )
        conn.commit()


def test_per_run_sse_scoped(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            collected = []
            async with client.stream(
                "GET",
                "/runs/run-sse-1/live",
                params={"since": 0},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            ) as resp:
                async for line in resp.aiter_lines():
                    collected.append(line)
                    if "run.completed" in line:
                        break
                    if len(collected) > 30:
                        break
            return "\n".join(collected)

    text = asyncio.run(_test())
    assert "step.started" in text
    assert "run.completed" in text
    # Should NOT contain events from other runs
    assert "run-other" not in text


def test_per_run_sse_stops_on_completion(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            lines = []
            async with client.stream(
                "GET",
                "/runs/run-sse-1/live",
                params={"since": 0},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            ) as resp:
                async for line in resp.aiter_lines():
                    lines.append(line)
            return lines

    lines = asyncio.run(_test())
    # The stream should end after run.completed
    data_lines = [l for l in lines if l.startswith("data:")]
    assert len(data_lines) == 2  # step.started + run.completed
