"""Tests for web authentication and draft action responses."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from matteros.core.store import SQLiteStore
from matteros.drafts.manager import DraftManager
from matteros.web.app import AUTH_QUERY_PARAM, create_app


def _make_client(home: Path) -> tuple[TestClient, str]:
    app = create_app(home=home)
    token = str(app.state.web_token)
    return TestClient(app), token


def test_web_rejects_missing_auth(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    client, _ = _make_client(home)

    response = client.get("/")
    assert response.status_code == 401


def test_web_accepts_bearer_or_bootstrap_query_and_sets_cookie(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    client, token = _make_client(home)

    by_header = client.get("/api/runs", headers={"Authorization": f"Bearer {token}"})
    assert by_header.status_code == 200

    by_query = client.get(f"/?{AUTH_QUERY_PARAM}={token}")
    assert by_query.status_code == 200
    assert "matteros_session" in by_query.cookies

    by_cookie = client.get("/api/runs")
    assert by_cookie.status_code == 200


def test_draft_approve_endpoint_returns_204_for_htmx_delete(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(home / "matteros.db")
    manager = DraftManager(store)
    draft_id = manager.create_draft(
        run_id="run-1",
        entry={
            "matter_id": "MAT-123",
            "duration_minutes": 30,
            "narrative": "Draft entry",
            "confidence": 0.9,
        },
    )

    client, token = _make_client(home)
    response = client.post(f"/drafts/{draft_id}/approve?{AUTH_QUERY_PARAM}={token}")
    assert response.status_code == 204
    assert response.text == ""

    updated = manager.get_draft(draft_id)
    assert updated is not None
    assert updated["status"] == "approved"
