from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class SlackConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="slack",
        description="Read and post messages via Slack Web API",
        default_mode=PermissionMode.READ,
        operations={
            "messages": PermissionMode.READ,
            "post_summary": PermissionMode.WRITE,
        },
    )

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("MATTEROS_SLACK_TOKEN", "")

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "messages":
            raise ConnectorError(f"unsupported slack read operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        token = self._resolve_token()
        channel = str(params.get("channel", ""))
        if not channel:
            raise ConnectorError("slack messages operation requires a channel param")

        url = "https://slack.com/api/conversations.history"
        query: dict[str, str] = {"channel": channel, "limit": str(params.get("limit", 200))}
        oldest = params.get("oldest")
        if oldest:
            query["oldest"] = str(oldest)
        latest = params.get("latest")
        if latest:
            query["latest"] = str(latest)

        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Slack API request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            if not payload.get("ok"):
                raise ConnectorError(f"Slack API error: {payload.get('error', 'unknown')}")
            return payload.get("messages", [])

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        if operation != "post_summary":
            raise ConnectorError(f"unsupported slack write operation: {operation}")

        token = self._resolve_token()
        channel = str(params.get("channel", ""))
        if not channel:
            raise ConnectorError("slack post_summary operation requires a channel param")

        text = str(payload) if not isinstance(payload, str) else payload

        url = "https://slack.com/api/chat.postMessage"
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                url,
                json={"channel": channel, "text": text},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Slack API request failed: {response.status_code} {response.text}"
                )
            result = response.json()
            if not result.get("ok"):
                raise ConnectorError(f"Slack API error: {result.get('error', 'unknown')}")
            return result

    def _resolve_token(self) -> str:
        if not self.token:
            raise ConnectorError(
                "Slack token not configured. Set MATTEROS_SLACK_TOKEN or pass token to constructor."
            )
        return self.token

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock slack payload must be a list")
        return data
