from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class GitHubConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="github",
        description="Read commits and pull requests from GitHub API",
        default_mode=PermissionMode.READ,
        operations={
            "commits": PermissionMode.READ,
            "prs": PermissionMode.READ,
        },
    )

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("MATTEROS_GITHUB_TOKEN", "")

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation not in ("commits", "prs"):
            raise ConnectorError(f"unsupported github read operation: {operation}")

        mock_file = params.get("mock_file")
        if isinstance(mock_file, str) and mock_file:
            return self._load_mock(Path(mock_file))

        if operation == "commits":
            return self._fetch_commits(params)
        return self._fetch_prs(params)

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("github connector is read-only")

    def _fetch_commits(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = self._resolve_token()
        repo = str(params.get("repo", ""))
        if not repo:
            raise ConnectorError("github commits operation requires a repo param (owner/repo)")

        url = f"https://api.github.com/repos/{repo}/commits"
        query: dict[str, str] = {"per_page": str(params.get("per_page", 100))}
        since = params.get("since")
        if since:
            query["since"] = str(since)
        until = params.get("until")
        if until:
            query["until"] = str(until)
        author = params.get("author")
        if author:
            query["author"] = str(author)

        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=query, headers=self._auth_headers(token))
            if response.status_code >= 400:
                raise ConnectorError(
                    f"GitHub API request failed: {response.status_code} {response.text}"
                )
            data = response.json()
            if not isinstance(data, list):
                raise ConnectorError("unexpected GitHub commits response shape")
            return data

    def _fetch_prs(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = self._resolve_token()
        repo = str(params.get("repo", ""))
        if not repo:
            raise ConnectorError("github prs operation requires a repo param (owner/repo)")

        url = f"https://api.github.com/repos/{repo}/pulls"
        query: dict[str, str] = {
            "per_page": str(params.get("per_page", 100)),
            "state": str(params.get("state", "all")),
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=query, headers=self._auth_headers(token))
            if response.status_code >= 400:
                raise ConnectorError(
                    f"GitHub API request failed: {response.status_code} {response.text}"
                )
            data = response.json()
            if not isinstance(data, list):
                raise ConnectorError("unexpected GitHub PRs response shape")
            return data

    def _resolve_token(self) -> str:
        if not self.token:
            raise ConnectorError(
                "GitHub token not configured. Set MATTEROS_GITHUB_TOKEN or pass token to constructor."
            )
        return self.token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _load_mock(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConnectorError(f"mock file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ConnectorError("mock github payload must be a list")
        return data
