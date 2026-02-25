from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class JiraConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="jira",
        description="Read worklogs/issues and log time via Jira REST API",
        default_mode=PermissionMode.READ,
        operations={
            "worklogs": PermissionMode.READ,
            "issues": PermissionMode.READ,
            "log_time": PermissionMode.WRITE,
        },
    )

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self.token = token or os.environ.get("MATTEROS_JIRA_TOKEN", "")
        self.base_url = (base_url or os.environ.get("MATTEROS_JIRA_URL", "")).rstrip("/")

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation not in ("worklogs", "issues"):
            raise ConnectorError(f"unsupported jira read operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        if operation == "worklogs":
            return self._fetch_worklogs(params)
        return self._fetch_issues(params)

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        if operation != "log_time":
            raise ConnectorError(f"unsupported jira write operation: {operation}")

        token = self._resolve_token()
        base = self._resolve_base_url()
        issue_key = str(params.get("issue_key", ""))
        if not issue_key:
            raise ConnectorError("jira log_time operation requires an issue_key param")

        url = f"{base}/rest/api/3/issue/{issue_key}/worklog"
        body = payload if isinstance(payload, dict) else {"timeSpentSeconds": int(payload)}

        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                url,
                json=body,
                headers=self._auth_headers(token),
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Jira API request failed: {response.status_code} {response.text}"
                )
            return response.json()

    def _fetch_worklogs(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = self._resolve_token()
        base = self._resolve_base_url()
        issue_key = str(params.get("issue_key", ""))
        if not issue_key:
            raise ConnectorError("jira worklogs operation requires an issue_key param")

        url = f"{base}/rest/api/3/issue/{issue_key}/worklog"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._auth_headers(token))
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Jira API request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            return payload.get("worklogs", [])

    def _fetch_issues(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = self._resolve_token()
        base = self._resolve_base_url()
        jql = str(params.get("jql", "assignee = currentUser() ORDER BY updated DESC"))
        max_results = int(params.get("max_results", 50))

        url = f"{base}/rest/api/3/search"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                url,
                params={"jql": jql, "maxResults": str(max_results)},
                headers=self._auth_headers(token),
            )
            if response.status_code >= 400:
                raise ConnectorError(
                    f"Jira API request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            return payload.get("issues", [])

    def _resolve_token(self) -> str:
        if not self.token:
            raise ConnectorError(
                "Jira token not configured. Set MATTEROS_JIRA_TOKEN or pass token to constructor."
            )
        return self.token

    def _resolve_base_url(self) -> str:
        if not self.base_url:
            raise ConnectorError(
                "Jira base URL not configured. Set MATTEROS_JIRA_URL or pass base_url to constructor."
            )
        return self.base_url

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock jira payload must be a list")
        return data
