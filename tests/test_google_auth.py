"""Tests for the Google auth token manager."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from matteros.connectors.google_auth import GoogleTokenManager


def test_env_token_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTEROS_GOOGLE_TOKEN", "env-token-123")
    manager = GoogleTokenManager()
    assert manager.get_token() == "env-token-123"


def test_cache_round_trip(tmp_path: Path) -> None:
    cache_file = tmp_path / "auth" / "google_token.json"
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    cache_data = {
        "access_token": "cached-token-abc",
        "expires_at": future,
        "refresh_token": "refresh-xyz",
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    manager = GoogleTokenManager(cache_path=cache_file)
    # Clear env var to ensure we use cache
    import os
    os.environ.pop("MATTEROS_GOOGLE_TOKEN", None)
    assert manager.get_token() == "cached-token-abc"


def test_refresh_mock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "auth" / "google_token.json"
    # Cache with expired token but valid refresh token
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    cache_data = {
        "access_token": "expired-token",
        "expires_at": past,
        "refresh_token": "refresh-token-123",
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    monkeypatch.delenv("MATTEROS_GOOGLE_TOKEN", raising=False)
    monkeypatch.setenv("MATTEROS_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("MATTEROS_GOOGLE_CLIENT_SECRET", "client-secret")

    def mock_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"access_token": "new-refreshed-token", "expires_in": 3600},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    manager = GoogleTokenManager(cache_path=cache_file)
    token = manager.get_token()
    assert token == "new-refreshed-token"

    # Verify cache was updated
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["access_token"] == "new-refreshed-token"
