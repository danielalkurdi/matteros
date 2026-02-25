from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class TogglConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="toggl",
        description="Read and create time entries via Toggl Track API",
        default_mode=PermissionMode.READ,
        operations={
            "time_entries": PermissionMode.READ,
            "create_time_entry": PermissionMode.WRITE,
        },
    )

    BASE_URL = "https://api.track.toggl.com/api/v9"

    def __init__(self, api_token: str | None = None) -> None:
        self.api_token = api_token or os.environ.get("MATTEROS_TOGGL_TOKEN", "")

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "time_entries":
            raise ConnectorError(f"unsupported toggl read operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        return self._fetch_time_entries(params)

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        if operation != "create_time_entry":
            raise ConnectorError(f"unsupported toggl write operation: {operation}")

        return self._create_time_entry(params, payload)

    def _fetch_time_entries(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = self._resolve_token()
        url = f"{self.BASE_URL}/me/time_entries"
        query: dict[str, str] = {}
        start = params.get("start")
        if start:
            query["start_date"] = str(start)[:10]
        end = params.get("end")
        if end:
            query["end_date"] = str(end)[:10]

        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                url,
                params=query,
                auth=(token, "api_token"),
            )
            if resp.status_code == 403:
                raise ConnectorError("Toggl authentication failed: check MATTEROS_TOGGL_TOKEN")
            if resp.status_code >= 400:
                raise ConnectorError(f"Toggl API error: {resp.status_code} {resp.text}")
            data = resp.json()

        if not isinstance(data, list):
            raise ConnectorError("unexpected Toggl time entries response shape")
        return data

    def _create_time_entry(self, params: dict[str, Any], payload: Any) -> dict[str, Any]:
        token = self._resolve_token()
        workspace_id = params.get("workspace_id") or os.environ.get("MATTEROS_TOGGL_WORKSPACE_ID", "")
        if not workspace_id:
            raise ConnectorError("workspace_id is required for toggl write operations")

        url = f"{self.BASE_URL}/workspaces/{workspace_id}/time_entries"

        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                url,
                json=payload,
                auth=(token, "api_token"),
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 403:
                raise ConnectorError("Toggl authentication failed: check MATTEROS_TOGGL_TOKEN")
            if resp.status_code >= 400:
                raise ConnectorError(f"Toggl API error: {resp.status_code} {resp.text}")
            return resp.json()

    def _resolve_token(self) -> str:
        if not self.api_token:
            raise ConnectorError(
                "Toggl API token not configured. Set MATTEROS_TOGGL_TOKEN or pass api_token to constructor."
            )
        return self.api_token

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock toggl payload must be a list")
        return data
