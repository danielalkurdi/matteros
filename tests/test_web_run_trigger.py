"""Tests for POST /api/runs endpoint."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from matteros.core.store import SQLiteStore
from matteros.web.app import create_app


def _init_home(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    SQLiteStore(home / "matteros.db")


def _make_client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def test_post_returns_run_id(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)

    # Create a playbook
    pb_dir = tmp_path / "playbooks"
    pb_dir.mkdir()
    (pb_dir / "test_playbook.yml").write_text(
        "metadata:\n  name: test_playbook\n  description: test\n  version: '1.0'\n"
        "connectors: []\ninputs: {}\nsteps:\n- id: noop\n  type: collect\n  config: {}\n"
    )

    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        async with _make_client(app) as client:
            resp = await client.post(
                "/api/runs",
                json={"playbook": "test_playbook", "inputs": {}, "dry_run": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp

    resp = asyncio.run(_test())
    assert resp.status_code == 201
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "started"


def test_post_validates_missing_playbook(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        async with _make_client(app) as client:
            resp = await client.post(
                "/api/runs",
                json={"inputs": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp

    resp = asyncio.run(_test())
    assert resp.status_code == 422


def test_post_rejects_unknown_playbook(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        async with _make_client(app) as client:
            resp = await client.post(
                "/api/runs",
                json={"playbook": "nonexistent_playbook"},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp

    resp = asyncio.run(_test())
    assert resp.status_code == 404


def test_post_requires_auth(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)
    app = create_app(home=home)

    async def _test():
        async with _make_client(app) as client:
            resp = await client.post(
                "/api/runs",
                json={"playbook": "test"},
            )
            return resp

    resp = asyncio.run(_test())
    assert resp.status_code == 401


def test_post_dry_run_defaults_true(tmp_path):
    home = tmp_path / "matteros"
    _init_home(home)

    pb_dir = tmp_path / "playbooks"
    pb_dir.mkdir()
    (pb_dir / "test_pb.yml").write_text(
        "metadata:\n  name: test_pb\n  description: test\n  version: '1.0'\n"
        "connectors: []\ninputs: {}\nsteps:\n- id: noop\n  type: collect\n  config: {}\n"
    )

    app = create_app(home=home)
    token = app.state.web_token

    async def _test():
        async with _make_client(app) as client:
            resp = await client.post(
                "/api/runs",
                json={"playbook": "test_pb"},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp

    resp = asyncio.run(_test())
    # Should succeed (dry_run defaults to True)
    assert resp.status_code == 201
