from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from matteros.connectors.base import ConnectorError

DEFAULT_SCOPES = "offline_access User.Read Mail.Read Calendars.Read"


@dataclass(slots=True)
class DeviceCodePrompt:
    user_code: str
    verification_uri: str
    message: str
    expires_in: int
    interval: int


class MicrosoftGraphTokenManager:
    def __init__(
        self,
        *,
        cache_path: Path,
        tenant_id: str | None = None,
        client_id: str | None = None,
        scopes: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.cache_path = cache_path
        self.tenant_id = tenant_id or os.getenv("MATTEROS_MS_TENANT_ID", "common")
        self.client_id = client_id or os.getenv("MATTEROS_MS_GRAPH_CLIENT_ID")
        self.scopes = scopes or os.getenv("MATTEROS_MS_GRAPH_SCOPES", DEFAULT_SCOPES)
        self.timeout_seconds = timeout_seconds

    def get_access_token(self, *, interactive: bool = False) -> str:
        env_token = os.getenv("MATTEROS_MS_GRAPH_TOKEN")
        if env_token:
            return env_token

        cached = self.load_cache()
        if cached and self._is_valid(cached):
            return str(cached["access_token"])

        if cached and cached.get("refresh_token"):
            refreshed = self._refresh_token(str(cached["refresh_token"]))
            self.save_cache(refreshed)
            return str(refreshed["access_token"])

        if not interactive:
            raise ConnectorError(
                "No usable Microsoft Graph token found. Run `matteros auth login` or set MATTEROS_MS_GRAPH_TOKEN."
            )

        token_payload = self.login_device_code(print_fn=print)
        return str(token_payload["access_token"])

    def login_device_code(self, *, print_fn: Callable[[str], None]) -> dict[str, Any]:
        self._require_client_id()

        prompt, device_code = self._request_device_code()
        print_fn(prompt.message)

        token_payload = self._poll_for_token(device_code, prompt.interval, prompt.expires_in)
        self.save_cache(token_payload)
        return token_payload

    def cache_status(self) -> dict[str, Any]:
        cached = self.load_cache()
        if not cached:
            return {"status": "missing"}

        now = int(time.time())
        expires_at = int(cached.get("expires_at", 0))
        return {
            "status": "valid" if expires_at > now + 120 else "expired",
            "tenant_id": cached.get("tenant_id"),
            "client_id": cached.get("client_id"),
            "scopes": cached.get("scope"),
            "expires_at": expires_at,
            "seconds_remaining": max(0, expires_at - now),
        }

    def load_cache(self) -> dict[str, Any] | None:
        if not self.cache_path.exists():
            return None

        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return None

        return payload

    def save_cache(self, payload: dict[str, Any]) -> None:
        access_token = str(payload.get("access_token", ""))
        refresh_token = payload.get("refresh_token")
        expires_in = int(payload.get("expires_in", 0))

        if not access_token:
            raise ConnectorError("cannot cache microsoft token without access_token")

        expires_at = int(time.time()) + max(0, expires_in)
        cache_payload = {
            "provider": "microsoft_graph",
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "scope": payload.get("scope", self.scopes),
            "token_type": payload.get("token_type", "Bearer"),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "obtained_at": int(time.time()),
        }

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache_payload, indent=2, sort_keys=True), encoding="utf-8")

    def _is_valid(self, payload: dict[str, Any]) -> bool:
        expires_at = int(payload.get("expires_at", 0))
        now = int(time.time())
        return bool(payload.get("access_token")) and expires_at > now + 120

    def _require_client_id(self) -> str:
        if not self.client_id:
            raise ConnectorError(
                "MATTEROS_MS_GRAPH_CLIENT_ID is required. Set env var or pass --client-id to auth login."
            )
        return self.client_id

    def _request_device_code(self) -> tuple[DeviceCodePrompt, str]:
        client_id = self._require_client_id()
        payload = self._post_form(
            self._device_code_url,
            {
                "client_id": client_id,
                "scope": self.scopes,
            },
        )

        device_code = str(payload.get("device_code", ""))
        if not device_code:
            raise ConnectorError("device code response missing device_code")

        prompt = DeviceCodePrompt(
            user_code=str(payload.get("user_code", "")),
            verification_uri=str(payload.get("verification_uri", "")),
            message=str(payload.get("message", "")),
            expires_in=int(payload.get("expires_in", 900)),
            interval=int(payload.get("interval", 5)),
        )
        return prompt, device_code

    def _poll_for_token(self, device_code: str, interval_seconds: int, expires_in: int) -> dict[str, Any]:
        client_id = self._require_client_id()
        deadline = time.time() + expires_in
        interval = max(1, interval_seconds)

        while time.time() < deadline:
            payload = self._post_form(
                self._token_url,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": device_code,
                },
                allow_oauth_errors=True,
            )

            error = payload.get("error")
            if not error:
                return payload

            error_text = str(error)
            if error_text == "authorization_pending":
                time.sleep(interval)
                continue
            if error_text == "slow_down":
                interval += 2
                time.sleep(interval)
                continue
            if error_text in {"expired_token", "authorization_declined", "bad_verification_code"}:
                raise ConnectorError(f"device login failed: {error_text}")

            description = str(payload.get("error_description", "")).strip()
            raise ConnectorError(f"device login error: {error_text} {description}")

        raise ConnectorError("device login timed out before authorization completed")

    def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        client_id = self._require_client_id()
        payload = self._post_form(
            self._token_url,
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
                "scope": self.scopes,
            },
            allow_oauth_errors=True,
        )

        error = payload.get("error")
        if error:
            description = str(payload.get("error_description", "")).strip()
            raise ConnectorError(f"refresh token request failed: {error} {description}")

        return payload

    def _post_form(
        self,
        url: str,
        form: dict[str, str],
        *,
        allow_oauth_errors: bool = False,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, data=form)
            payload = response.json()

        if response.status_code >= 400 and not allow_oauth_errors:
            description = payload.get("error_description", "") if isinstance(payload, dict) else ""
            raise ConnectorError(f"microsoft oauth request failed: {response.status_code} {description}")

        if not isinstance(payload, dict):
            raise ConnectorError("unexpected microsoft oauth response format")

        return payload

    @property
    def _authority(self) -> str:
        tenant = self.tenant_id or "common"
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

    @property
    def _device_code_url(self) -> str:
        return f"{self._authority}/devicecode"

    @property
    def _token_url(self) -> str:
        return f"{self._authority}/token"
