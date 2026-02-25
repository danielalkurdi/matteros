"""Tests for the Google Calendar connector."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from matteros.connectors.base import ConnectorError
from matteros.connectors.google_calendar import GoogleCalendarConnector


@pytest.fixture()
def mock_events(tmp_path: Path) -> Path:
    events = [
        {
            "id": "evt-1",
            "summary": "MAT-100 Strategy meeting",
            "start": {"dateTime": "2024-06-15T10:00:00Z"},
            "end": {"dateTime": "2024-06-15T11:00:00Z"},
        },
        {
            "id": "evt-2",
            "summary": "Lunch break",
            "start": {"dateTime": "2024-06-15T12:00:00Z"},
            "end": {"dateTime": "2024-06-15T13:00:00Z"},
        },
    ]
    mock_file = tmp_path / "google_calendar_events.json"
    mock_file.write_text(json.dumps(events), encoding="utf-8")
    return mock_file


def test_read_mock_file(mock_events: Path) -> None:
    connector = GoogleCalendarConnector()
    result = connector.read("events", {"mock_file": str(mock_events)}, {})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["summary"] == "MAT-100 Strategy meeting"


def test_read_unsupported_operation() -> None:
    connector = GoogleCalendarConnector()
    with pytest.raises(ConnectorError, match="unsupported google_calendar read operation"):
        connector.read("meetings", {}, {})


def test_write_raises() -> None:
    connector = GoogleCalendarConnector()
    with pytest.raises(ConnectorError, match="read-only"):
        connector.write("events", {}, {}, {})


def test_fetch_events_mock_http(monkeypatch: pytest.MonkeyPatch) -> None:
    token_manager = MagicMock()
    token_manager.get_token.return_value = "fake-token"

    response_data = {"items": [{"id": "evt-1", "summary": "Test event"}]}

    def mock_get(self, url, **kwargs):
        resp = httpx.Response(200, json=response_data, request=httpx.Request("GET", url))
        return resp

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    connector = GoogleCalendarConnector(token_manager=token_manager)
    result = connector.read("events", {"start": "2024-06-15T00:00:00Z"}, {})
    assert len(result) == 1
    assert result[0]["summary"] == "Test event"
    token_manager.get_token.assert_called_once()
