"""Tests for new connectors (slack, jira, github, ical)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from matteros.connectors.github_connector import GitHubConnector
from matteros.connectors.ical import ICalConnector
from matteros.connectors.jira import JiraConnector
from matteros.connectors.slack import SlackConnector
from matteros.core.types import PermissionMode


def test_slack_connector_manifest() -> None:
    c = SlackConnector(token="test")
    assert c.manifest.connector_id == "slack"
    assert "messages" in c.manifest.operations
    assert c.manifest.operations["messages"] == PermissionMode.READ
    assert "post_summary" in c.manifest.operations
    assert c.manifest.operations["post_summary"] == PermissionMode.WRITE


def test_slack_read_from_mock(tmp_path: Path) -> None:
    mock_data = [{"text": "hello", "ts": "1234567890.000"}]
    mock_file = tmp_path / "slack_messages.json"
    mock_file.write_text(json.dumps(mock_data), encoding="utf-8")

    c = SlackConnector(token="test")
    result = c.read("messages", {"mock_file": str(mock_file)}, {})
    assert len(result) == 1
    assert result[0]["text"] == "hello"


def test_jira_connector_manifest() -> None:
    c = JiraConnector(token="test", base_url="https://test.atlassian.net")
    assert c.manifest.connector_id == "jira"
    assert "worklogs" in c.manifest.operations
    assert "issues" in c.manifest.operations
    assert "log_time" in c.manifest.operations


def test_jira_read_from_mock(tmp_path: Path) -> None:
    mock_data = [{"key": "PROJ-1", "fields": {"summary": "Test issue"}}]
    mock_file = tmp_path / "jira_issues.json"
    mock_file.write_text(json.dumps(mock_data), encoding="utf-8")

    c = JiraConnector(token="test", base_url="https://test.atlassian.net")
    result = c.read("issues", {"mock_file": str(mock_file)}, {})
    assert len(result) == 1


def test_github_connector_manifest() -> None:
    c = GitHubConnector(token="test")
    assert c.manifest.connector_id == "github"
    assert "commits" in c.manifest.operations
    assert "prs" in c.manifest.operations


def test_github_read_from_mock(tmp_path: Path) -> None:
    mock_data = [{"sha": "abc123", "commit": {"message": "test"}}]
    mock_file = tmp_path / "github_commits.json"
    mock_file.write_text(json.dumps(mock_data), encoding="utf-8")

    c = GitHubConnector(token="test")
    result = c.read("commits", {"mock_file": str(mock_file)}, {})
    assert len(result) == 1


def test_ical_connector_manifest() -> None:
    c = ICalConnector()
    assert c.manifest.connector_id == "ical"
    assert "events" in c.manifest.operations


def test_ical_read_from_ics(tmp_path: Path) -> None:
    ics_content = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260220T090000Z
DTEND:20260220T100000Z
SUMMARY:MAT-123 Team meeting
UID:test-event-1
END:VEVENT
END:VCALENDAR"""
    ics_file = tmp_path / "test.ics"
    ics_file.write_text(ics_content, encoding="utf-8")

    c = ICalConnector()
    result = c.read("events", {"path": str(ics_file)}, {})
    assert len(result) == 1
    assert "MAT-123" in result[0].get("summary", "")
