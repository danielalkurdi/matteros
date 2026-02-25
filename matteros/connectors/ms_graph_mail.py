from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.connectors.ms_graph_auth import MicrosoftGraphTokenManager
from matteros.core.types import ConnectorManifest, PermissionMode


class MicrosoftGraphMailConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="ms_graph_mail",
        description="Read sent messages from Microsoft Graph",
        default_mode=PermissionMode.READ,
        operations={"sent_emails": PermissionMode.READ},
    )

    def __init__(self, token_manager: MicrosoftGraphTokenManager | None = None) -> None:
        self.token_manager = token_manager

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "sent_emails":
            raise ConnectorError(f"unsupported mail operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        token = self._resolve_token()

        start = str(params.get("start", ""))
        end = str(params.get("end", ""))
        url = "https://graph.microsoft.com/v1.0/me/mailFolders/SentItems/messages"
        query = {
            "$select": "id,subject,sentDateTime,toRecipients,conversationId",
            "$top": "200",
        }

        items: list[dict[str, Any]] = []
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                url,
                params=query,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Microsoft Graph mail request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            values = payload.get("value", [])
            for item in values:
                sent_at = item.get("sentDateTime")
                if sent_at and self._in_range(sent_at, start, end):
                    items.append(item)

        return items

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("mail connector is read-only")

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
            raise ConnectorError("mock mail payload must be a list")
        return data

    def _in_range(self, value: str, start: str, end: str) -> bool:
        item_dt = self._parse_iso(value)
        if start:
            start_dt = self._parse_iso(start)
            if item_dt < start_dt:
                return False
        if end:
            end_dt = self._parse_iso(end)
            if item_dt > end_dt:
                return False
        return True

    def _parse_iso(self, value: str) -> datetime:
        clean = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
