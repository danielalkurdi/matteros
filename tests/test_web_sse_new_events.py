"""Test that audit API includes draft.created events for SSE consumption."""

from __future__ import annotations

import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from matteros.core.store import SQLiteStore
from matteros.web.app import create_app


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(home / "matteros.db")
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (run_id, timestamp, event_type, actor, step_id, data_json, prev_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-1", "2024-01-01T00:00:00Z", "draft.created", "system", None, json.dumps({"draft_id": "d-1"}), None, "hash1"),
        )
        conn.commit()


def test_audit_api_includes_draft_created_event(tmp_path):
    import asyncio

    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/audit",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()

    events = asyncio.run(_test())
    event_types = [e.get("event_type") for e in events]
    assert "draft.created" in event_types
