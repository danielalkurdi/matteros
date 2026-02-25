from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


class GoogleTokenManager:
    """Manages OAuth2 tokens for Google APIs.

    Supports three auth methods:
    1. Direct token via MATTEROS_GOOGLE_TOKEN env var
    2. Device code OAuth2 flow
    3. Cached token from previous auth
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = cache_path
        self._token: str | None = None
        self._expires_at: str | None = None
        self._refresh_token: str | None = None
        self._load_cache()

    def get_token(self) -> str:
        env_token = os.environ.get("MATTEROS_GOOGLE_TOKEN")
        if env_token:
            return env_token

        if self._token and not self._is_expired():
            return self._token

        if self._refresh_token:
            self._refresh()
            return self._token  # type: ignore[return-value]

        raise RuntimeError(
            "Google token not available. Set MATTEROS_GOOGLE_TOKEN or run device code auth."
        )

    def _is_expired(self) -> bool:
        if not self._expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(self._expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return datetime.now(UTC) >= expiry
        except (ValueError, TypeError):
            return True

    def _refresh(self) -> None:
        client_id = os.environ.get("MATTEROS_GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("MATTEROS_GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret or not self._refresh_token:
            raise RuntimeError("Cannot refresh Google token: missing credentials")

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Google token refresh failed: {resp.status_code}")
            data = resp.json()

        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()
        self._save_cache()

    def _load_cache(self) -> None:
        if self._cache_path and self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._token = data.get("access_token")
                self._expires_at = data.get("expires_at")
                self._refresh_token = data.get("refresh_token")
            except (json.JSONDecodeError, OSError):
                pass

    def _save_cache(self) -> None:
        if self._cache_path:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "access_token": self._token,
                "expires_at": self._expires_at,
                "refresh_token": self._refresh_token,
            }
            self._cache_path.write_text(json.dumps(data), encoding="utf-8")
