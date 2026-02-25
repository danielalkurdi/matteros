from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class GoogleCalendarConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="google_calendar",
        description="Read calendar events from Google Calendar API",
        default_mode=PermissionMode.READ,
        operations={"events": PermissionMode.READ},
    )

    def __init__(self, token_manager=None) -> None:
        self._token_manager = token_manager

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "events":
            raise ConnectorError(f"unsupported google_calendar read operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        return self._fetch_events(params)

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("google_calendar connector is read-only")

    def _fetch_events(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self._token_manager is None:
            raise ConnectorError("Google Calendar requires a token manager")
        token = self._token_manager.get_token()

        calendar_id = params.get("calendar_id", "primary")
        time_min = params.get("start", params.get("time_min", ""))
        time_max = params.get("end", params.get("time_max", ""))

        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        query: dict[str, str] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(params.get("max_results", 250)),
        }
        if time_min:
            query["timeMin"] = str(time_min)
        if time_max:
            query["timeMax"] = str(time_max)

        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code >= 400:
                raise ConnectorError(f"Google Calendar API error: {resp.status_code} {resp.text}")
            data = resp.json()

        items = data.get("items", [])
        if not isinstance(items, list):
            raise ConnectorError("unexpected Google Calendar response shape")
        return items

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock google calendar payload must be a list")
        return data
