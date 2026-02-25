"""Tests for the Toggl connector."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from matteros.connectors.base import ConnectorError
from matteros.connectors.toggl import TogglConnector


@pytest.fixture()
def mock_entries(tmp_path: Path) -> Path:
    entries = [
        {
            "id": 12345,
            "description": "MAT-100 Research",
            "duration": 3600,
            "start": "2024-06-15T10:00:00+00:00",
        },
        {
            "id": 12346,
            "description": "Admin tasks",
            "duration": 1800,
            "start": "2024-06-15T14:00:00+00:00",
        },
    ]
    mock_file = tmp_path / "toggl_entries.json"
    mock_file.write_text(json.dumps(entries), encoding="utf-8")
    return mock_file


def test_read_mock_file(mock_entries: Path) -> None:
    connector = TogglConnector(api_token="fake")
    result = connector.read("time_entries", {"mock_file": str(mock_entries)}, {})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["description"] == "MAT-100 Research"


def test_write_mock_http(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {"id": 99, "description": "New entry", "duration": 600}

    def mock_post(self, url, **kwargs):
        return httpx.Response(200, json=created, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    connector = TogglConnector(api_token="fake-token")
    payload = {"description": "New entry", "duration": 600, "start": "2024-06-15T10:00:00Z"}
    result = connector.write("create_time_entry", {"workspace_id": "12345"}, payload, {})
    assert result["id"] == 99


def test_auth_error() -> None:
    connector = TogglConnector(api_token="")
    with pytest.raises(ConnectorError, match="Toggl API token not configured"):
        connector.read("time_entries", {}, {})
