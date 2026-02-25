"""Tests for the skills/draft_time_entries module."""

from __future__ import annotations

from datetime import UTC, datetime

from matteros.skills.draft_time_entries import (
    cluster_activities,
    draft_time_entries_from_clusters,
    flatten_activity_inputs,
    infer_matter_id,
    parse_iso,
)


# -- parse_iso ----------------------------------------------------------------


def test_parse_iso_valid_iso_string() -> None:
    result = parse_iso("2024-06-15T10:30:00+00:00")
    assert result is not None
    assert result.tzinfo is not None
    assert result.hour == 10


def test_parse_iso_z_suffix() -> None:
    result = parse_iso("2024-06-15T10:30:00Z")
    assert result is not None
    assert result.tzinfo is not None


def test_parse_iso_none_input() -> None:
    assert parse_iso(None) is None


def test_parse_iso_empty_string() -> None:
    assert parse_iso("") is None


def test_parse_iso_naive_datetime() -> None:
    result = parse_iso("2024-06-15T10:30:00")
    assert result is not None
    assert result.tzinfo is not None  # should get UTC


def test_parse_iso_garbage_string() -> None:
    try:
        parse_iso("not-a-date")
        assert False, "should have raised"
    except (ValueError, TypeError):
        pass


# -- infer_matter_id ----------------------------------------------------------


def test_infer_matter_id_mat_prefix() -> None:
    result = infer_matter_id(["Meeting about MAT-123 review"])
    assert "MAT-123" in result


def test_infer_matter_id_mtr_prefix() -> None:
    result = infer_matter_id(["Review MTR:foo-bar"])
    assert "MTR" in result


def test_infer_matter_id_matter_prefix() -> None:
    result = infer_matter_id(["Working on MATTER test-case"])
    assert "MATTER" in result


def test_infer_matter_id_no_match() -> None:
    assert infer_matter_id(["regular text here"]) == "UNASSIGNED"


def test_infer_matter_id_custom_fallback() -> None:
    assert infer_matter_id(["plain text here"], fallback="NONE") == "NONE"


# -- flatten_activity_inputs --------------------------------------------------


def test_flatten_calendar_events_nested() -> None:
    payload = {
        "calendar_events": [
            {
                "subject": "MAT-100 Strategy meeting",
                "start": {"dateTime": "2024-06-15T10:00:00Z"},
                "end": {"dateTime": "2024-06-15T11:00:00Z"},
                "id": "cal-1",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "calendar"
    assert result[0]["duration_minutes"] == 60
    assert "MAT-100" in result[0]["matter_id"]


def test_flatten_calendar_events_flat_start_end() -> None:
    payload = {
        "calendar_events": [
            {
                "subject": "Standup",
                "start": "2024-06-15T09:00:00Z",
                "end": "2024-06-15T09:30:00Z",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["duration_minutes"] == 30


def test_flatten_calendar_events_missing_dates() -> None:
    payload = {"calendar_events": [{"subject": "No dates"}]}
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["duration_minutes"] == 30  # default


def test_flatten_emails() -> None:
    payload = {
        "sent_emails": [
            {
                "subject": "Re: MAT-200 Document review",
                "sentDateTime": "2024-06-15T14:00:00Z",
                "id": "email-1",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "email"
    assert result[0]["duration_minutes"] == 6
    assert "MAT-200" in result[0]["matter_id"]


def test_flatten_file_activity() -> None:
    payload = {
        "file_activity": [
            {"path": "/docs/MAT-300/brief.docx", "modified_at": "2024-06-15T12:00:00Z"}
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "document"
    assert "MAT-300" in result[0]["matter_id"]


def test_flatten_file_activity_matter_hint() -> None:
    payload = {
        "file_activity": [{"path": "/docs/brief.docx"}],
        "matter_hint": "MAT-999",
    }
    result = flatten_activity_inputs(payload)
    assert "MAT-999" in result[0]["matter_id"]


def test_flatten_slack_messages() -> None:
    payload = {
        "slack_messages": [
            {"text": "Discussion about MAT-400 timeline", "ts": "1718451600.000000"}
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "message"
    assert result[0]["duration_minutes"] == 3
    assert result[0]["timestamp"] is not None


def test_flatten_slack_text_truncation() -> None:
    payload = {"slack_messages": [{"text": "x" * 200, "ts": "1718451600.0"}]}
    result = flatten_activity_inputs(payload)
    assert len(result[0]["title"]) <= 120


def test_flatten_jira_worklogs() -> None:
    payload = {
        "jira_worklogs": [
            {
                "comment": "MAT-500 research",
                "timeSpentSeconds": 3600,
                "started": "2024-06-15T10:00:00Z",
                "id": "wl-1",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "worklog"
    assert result[0]["duration_minutes"] == 60


def test_flatten_jira_worklogs_missing_fields() -> None:
    payload = {"jira_worklogs": [{"issueKey": "PROJ-1"}]}
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["duration_minutes"] == 6  # default when no seconds


def test_flatten_jira_issues() -> None:
    payload = {
        "jira_issues": [
            {
                "key": "MAT-600",
                "fields": {
                    "summary": "Investigate compliance issue",
                    "updated": "2024-06-15T10:00:00Z",
                },
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "issue"
    assert "MAT-600" in result[0]["title"]


def test_flatten_github_commits() -> None:
    payload = {
        "github_commits": [
            {
                "sha": "abc12345def67890",
                "commit": {
                    "message": "Fix MAT-700 billing bug\nDetails here",
                    "author": {"date": "2024-06-15T10:00:00Z"},
                },
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "commit"
    assert result[0]["evidence_ref"] == "abc12345"  # truncated to 8
    assert "\n" not in result[0]["title"]  # first line only


def test_flatten_github_prs() -> None:
    payload = {
        "github_prs": [
            {
                "title": "MAT-800 Add export feature",
                "number": 42,
                "created_at": "2024-06-15T10:00:00Z",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "pr"
    assert "PR #42" in result[0]["title"]
    assert result[0]["duration_minutes"] == 15


def test_flatten_ical_events() -> None:
    payload = {
        "ical_events": [
            {
                "summary": "MAT-900 Deposition prep",
                "dtstart": "2024-06-15T14:00:00Z",
                "dtend": "2024-06-15T15:30:00Z",
                "uid": "ical-1",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "calendar"
    assert result[0]["duration_minutes"] == 90


def test_flatten_handles_google_calendar_events() -> None:
    payload = {
        "google_calendar_events": [
            {
                "id": "gcal-1",
                "summary": "MAT-1000 Client call",
                "start": {"dateTime": "2024-06-15T10:00:00Z"},
                "end": {"dateTime": "2024-06-15T11:00:00Z"},
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "calendar"
    assert result[0]["duration_minutes"] == 60
    assert "MAT-1000" in result[0]["matter_id"]
    assert result[0]["evidence_ref"] == "gcal-1"


def test_flatten_handles_toggl_entries() -> None:
    payload = {
        "toggl_entries": [
            {
                "id": 55555,
                "description": "MAT-2000 Legal research",
                "duration": 5400,
                "start": "2024-06-15T14:00:00Z",
            }
        ]
    }
    result = flatten_activity_inputs(payload)
    assert len(result) == 1
    assert result[0]["kind"] == "time_entry"
    assert result[0]["duration_minutes"] == 90  # 5400 / 60
    assert "MAT-2000" in result[0]["matter_id"]
    assert result[0]["evidence_ref"] == "55555"


def test_flatten_empty_payload() -> None:
    assert flatten_activity_inputs({}) == []


# -- cluster_activities -------------------------------------------------------


def test_cluster_groups_by_matter() -> None:
    payload = {
        "calendar_events": [
            {"subject": "MAT-100 meeting", "start": "2024-06-15T10:00:00Z", "end": "2024-06-15T11:00:00Z"},
        ],
        "sent_emails": [
            {"subject": "MAT-100 follow-up", "sentDateTime": "2024-06-15T14:00:00Z"},
        ],
    }
    clusters = cluster_activities(payload)
    assert len(clusters) == 1
    assert clusters[0]["activity_count"] == 2
    assert "calendar" in clusters[0]["activity_types"]
    assert "email" in clusters[0]["activity_types"]


def test_cluster_sorts_by_total_desc() -> None:
    payload = {
        "calendar_events": [
            {"subject": "MAT-A meeting", "start": "2024-06-15T10:00:00Z", "end": "2024-06-15T12:00:00Z"},
        ],
        "sent_emails": [
            {"subject": "MAT-B email", "sentDateTime": "2024-06-15T14:00:00Z"},
        ],
    }
    clusters = cluster_activities(payload)
    assert len(clusters) == 2
    assert clusters[0]["total_minutes"] >= clusters[1]["total_minutes"]


# -- draft_time_entries_from_clusters -----------------------------------------


def test_draft_confidence_unassigned_penalty() -> None:
    clusters = [
        {
            "matter_id": "UNASSIGNED",
            "activity_count": 1,
            "activity_types": ["calendar"],
            "total_minutes": 30,
            "activities": [],
            "evidence_refs": [],
        }
    ]
    drafts = draft_time_entries_from_clusters(clusters)
    assert len(drafts) == 1
    assert drafts[0]["confidence"] == 0.45  # base only, no +0.25


def test_draft_confidence_assigned_boost() -> None:
    clusters = [
        {
            "matter_id": "MAT-100",
            "activity_count": 1,
            "activity_types": ["calendar"],
            "total_minutes": 30,
            "activities": [],
            "evidence_refs": [],
        }
    ]
    drafts = draft_time_entries_from_clusters(clusters)
    assert drafts[0]["confidence"] == 0.7  # 0.45 + 0.25


def test_draft_confidence_activity_count_boost() -> None:
    clusters = [
        {
            "matter_id": "MAT-100",
            "activity_count": 3,
            "activity_types": ["calendar"],
            "total_minutes": 60,
            "activities": [],
            "evidence_refs": [],
        }
    ]
    drafts = draft_time_entries_from_clusters(clusters)
    assert drafts[0]["confidence"] == 0.85  # 0.45 + 0.25 + 0.15


def test_draft_confidence_multi_type_boost() -> None:
    clusters = [
        {
            "matter_id": "MAT-100",
            "activity_count": 3,
            "activity_types": ["calendar", "email"],
            "total_minutes": 60,
            "activities": [],
            "evidence_refs": [],
        }
    ]
    drafts = draft_time_entries_from_clusters(clusters)
    assert drafts[0]["confidence"] == 0.95  # 0.45 + 0.25 + 0.15 + 0.10


def test_draft_confidence_capped_at_098() -> None:
    clusters = [
        {
            "matter_id": "MAT-100",
            "activity_count": 10,
            "activity_types": ["calendar", "email"],
            "total_minutes": 300,
            "activities": [],
            "evidence_refs": ["a"] * 25,
        }
    ]
    drafts = draft_time_entries_from_clusters(clusters)
    assert drafts[0]["confidence"] <= 0.98
