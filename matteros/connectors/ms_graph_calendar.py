from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.connectors.ms_graph_auth import MicrosoftGraphTokenManager
from matteros.core.types import ConnectorManifest, PermissionMode


class MicrosoftGraphCalendarConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="ms_graph_calendar",
        description="Read calendar events from Microsoft Graph",
        default_mode=PermissionMode.READ,
        operations={"events": PermissionMode.READ},
    )

    def __init__(self, token_manager: MicrosoftGraphTokenManager | None = None) -> None:
        self.token_manager = token_manager

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "events":
            raise ConnectorError(f"unsupported calendar operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        token = self._resolve_token()

        start = str(params.get("start", ""))
        end = str(params.get("end", ""))
        if not start or not end:
            raise ConnectorError("calendar operation requires start and end")

        url = "https://graph.microsoft.com/v1.0/me/calendarView"
        query = {
            "startDateTime": start,
            "endDateTime": end,
            "$top": "200",
            "$select": "id,subject,start,end,organizer,attendees,location",
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Microsoft Graph calendar request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            values = payload.get("value", [])
            if not isinstance(values, list):
                raise ConnectorError("unexpected calendar response shape")
            return values

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("calendar connector is read-only")

    def _resolve_token(self) -> str:
        if self.token_manager is None:
            raise ConnectorError(
                "Microsoft Graph auth is not configured. Recreate connector registry with a token manager."
            )
        return self.token_manager.get_access_token(interactive=False)

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock calendar payload must be a list")
        return data
