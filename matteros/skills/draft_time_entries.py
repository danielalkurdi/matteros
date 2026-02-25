from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


MATTER_PATTERN = re.compile(r"(?:MAT|MTR|MATTER)[-:\s]?([A-Za-z0-9_-]{2,})", re.IGNORECASE)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def infer_matter_id(texts: list[str], fallback: str = "UNASSIGNED") -> str:
    for text in texts:
        match = MATTER_PATTERN.search(text)
        if match:
            token = match.group(0).upper().replace(" ", "")
            return token.replace(":", "-")
    return fallback


def flatten_activity_inputs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calendar_events = payload.get("calendar_events", [])
    sent_emails = payload.get("sent_emails", [])
    file_activity = payload.get("file_activity", [])
    matter_hint = str(payload.get("matter_hint", "")).strip()

    normalized: list[dict[str, Any]] = []

    for event in calendar_events:
        subject = str(event.get("subject", "Calendar event"))
        start_value = (
            event.get("start", {}).get("dateTime")
            if isinstance(event.get("start"), dict)
            else event.get("start")
        )
        end_value = (
            event.get("end", {}).get("dateTime")
            if isinstance(event.get("end"), dict)
            else event.get("end")
        )

        start_dt = parse_iso(start_value)
        end_dt = parse_iso(end_value)
        duration = 30
        if start_dt and end_dt and end_dt > start_dt:
            duration = max(6, int((end_dt - start_dt).total_seconds() // 60))

        inferred = infer_matter_id([subject, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "calendar",
                "title": subject,
                "duration_minutes": duration,
                "timestamp": start_dt.isoformat() if start_dt else None,
                "matter_id": inferred,
                "evidence_ref": str(event.get("id", f"calendar:{len(normalized)}")),
            }
        )

    for email in sent_emails:
        subject = str(email.get("subject", "Sent email"))
        sent_at = parse_iso(str(email.get("sentDateTime", "")))
        inferred = infer_matter_id([subject, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "email",
                "title": subject,
                "duration_minutes": 6,
                "timestamp": sent_at.isoformat() if sent_at else None,
                "matter_id": inferred,
                "evidence_ref": str(email.get("id", f"email:{len(normalized)}")),
            }
        )

    for item in file_activity:
        path = str(item.get("path", item.get("name", "file")))
        inferred = infer_matter_id([path, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "document",
                "title": path,
                "duration_minutes": 5,
                "timestamp": item.get("modified_at"),
                "matter_id": inferred,
                "evidence_ref": path,
            }
        )

    for msg in payload.get("slack_messages", []):
        text = str(msg.get("text", "Slack message"))
        ts = msg.get("ts")
        timestamp = None
        if ts:
            try:
                timestamp = datetime.fromtimestamp(float(str(ts)), tz=UTC).isoformat()
            except (ValueError, OSError):
                pass
        inferred = infer_matter_id([text, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "message",
                "title": text[:120],
                "duration_minutes": 3,
                "timestamp": timestamp,
                "matter_id": inferred,
                "evidence_ref": str(msg.get("ts", f"slack:{len(normalized)}")),
            }
        )

    for wl in payload.get("jira_worklogs", []):
        comment = str(wl.get("comment", wl.get("issueKey", "Jira worklog")))
        seconds = int(wl.get("timeSpentSeconds", 0))
        duration = max(1, seconds // 60) if seconds else 6
        started = wl.get("started")
        timestamp = parse_iso(str(started)) if started else None
        inferred = infer_matter_id([comment, str(wl.get("issueKey", "")), matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "worklog",
                "title": comment[:120],
                "duration_minutes": duration,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "matter_id": inferred,
                "evidence_ref": str(wl.get("id", f"jira-wl:{len(normalized)}")),
            }
        )

    for issue in payload.get("jira_issues", []):
        summary = str(issue.get("fields", {}).get("summary", issue.get("key", "Jira issue")))
        key = str(issue.get("key", ""))
        updated = issue.get("fields", {}).get("updated")
        timestamp = parse_iso(str(updated)) if updated else None
        inferred = infer_matter_id([summary, key, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "issue",
                "title": f"{key}: {summary}" if key else summary,
                "duration_minutes": 10,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "matter_id": inferred,
                "evidence_ref": key or f"jira-issue:{len(normalized)}",
            }
        )

    for commit in payload.get("github_commits", []):
        message = str(commit.get("commit", {}).get("message", "GitHub commit"))
        sha = str(commit.get("sha", ""))[:8]
        commit_date = commit.get("commit", {}).get("author", {}).get("date")
        timestamp = parse_iso(str(commit_date)) if commit_date else None
        inferred = infer_matter_id([message, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "commit",
                "title": message.split("\n")[0][:120],
                "duration_minutes": 8,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "matter_id": inferred,
                "evidence_ref": sha or f"gh-commit:{len(normalized)}",
            }
        )

    for pr in payload.get("github_prs", []):
        title = str(pr.get("title", "GitHub PR"))
        number = pr.get("number", "")
        created = pr.get("created_at")
        timestamp = parse_iso(str(created)) if created else None
        inferred = infer_matter_id([title, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "pr",
                "title": f"PR #{number}: {title}" if number else title,
                "duration_minutes": 15,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "matter_id": inferred,
                "evidence_ref": f"pr:{number}" if number else f"gh-pr:{len(normalized)}",
            }
        )

    for event in payload.get("google_calendar_events", []):
        summary = str(event.get("summary", "Google Calendar event"))
        start_obj = event.get("start", {})
        end_obj = event.get("end", {})
        start_value = start_obj.get("dateTime") or start_obj.get("date")
        end_value = end_obj.get("dateTime") or end_obj.get("date")
        start_dt = parse_iso(start_value)
        end_dt = parse_iso(end_value)
        duration = 30
        if start_dt and end_dt and end_dt > start_dt:
            duration = max(6, int((end_dt - start_dt).total_seconds() // 60))
        inferred = infer_matter_id([summary, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "calendar",
                "title": summary,
                "duration_minutes": duration,
                "timestamp": start_dt.isoformat() if start_dt else None,
                "matter_id": inferred,
                "evidence_ref": str(event.get("id", f"gcal:{len(normalized)}")),
            }
        )

    for entry in payload.get("toggl_entries", []):
        description = str(entry.get("description", "Toggl time entry"))
        seconds = int(entry.get("duration", 0))
        duration = max(1, abs(seconds) // 60) if seconds else 6
        start_value = entry.get("start")
        start_dt = parse_iso(str(start_value)) if start_value else None
        inferred = infer_matter_id([description, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "time_entry",
                "title": description[:120],
                "duration_minutes": duration,
                "timestamp": start_dt.isoformat() if start_dt else None,
                "matter_id": inferred,
                "evidence_ref": str(entry.get("id", f"toggl:{len(normalized)}")),
            }
        )

    for event in payload.get("ical_events", []):
        summary = str(event.get("summary", "Calendar event"))
        start_dt = parse_iso(str(event.get("dtstart", "")))
        end_dt = parse_iso(str(event.get("dtend", "")))
        duration = 30
        if start_dt and end_dt and end_dt > start_dt:
            duration = max(6, int((end_dt - start_dt).total_seconds() // 60))
        inferred = infer_matter_id([summary, matter_hint], fallback="UNASSIGNED")
        normalized.append(
            {
                "kind": "calendar",
                "title": summary,
                "duration_minutes": duration,
                "timestamp": start_dt.isoformat() if start_dt else None,
                "matter_id": inferred,
                "evidence_ref": str(event.get("uid", f"ical:{len(normalized)}")),
            }
        )

    return normalized


def cluster_activities(payload: dict[str, Any]) -> list[dict[str, Any]]:
    activities = flatten_activity_inputs(payload)
    by_matter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for activity in activities:
        by_matter[str(activity.get("matter_id", "UNASSIGNED"))].append(activity)

    clusters: list[dict[str, Any]] = []
    for matter_id, items in by_matter.items():
        total_minutes = sum(int(item.get("duration_minutes", 0)) for item in items)
        types = sorted({str(item.get("kind", "activity")) for item in items})
        evidence_refs = [str(item.get("evidence_ref", "")) for item in items if item.get("evidence_ref")]
        clusters.append(
            {
                "matter_id": matter_id,
                "activity_count": len(items),
                "activity_types": types,
                "total_minutes": max(6, total_minutes),
                "activities": items,
                "evidence_refs": evidence_refs,
            }
        )

    clusters.sort(key=lambda item: item["total_minutes"], reverse=True)
    return clusters


def draft_time_entries_from_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for cluster in clusters:
        matter_id = str(cluster.get("matter_id", "UNASSIGNED"))
        activity_types = cluster.get("activity_types", [])
        activity_count = int(cluster.get("activity_count", 0))
        total_minutes = int(cluster.get("total_minutes", 0))
        evidence_refs = cluster.get("evidence_refs", [])

        type_phrase = ", ".join(activity_types) if activity_types else "general matter work"
        narrative = (
            f"Matter {matter_id}: reviewed and progressed {activity_count} activity item(s) "
            f"covering {type_phrase}."
        )

        confidence = 0.45
        if matter_id != "UNASSIGNED":
            confidence += 0.25
        if activity_count >= 3:
            confidence += 0.15
        if "calendar" in activity_types and "email" in activity_types:
            confidence += 0.1

        suggestions.append(
            {
                "matter_id": matter_id,
                "client_id": None,
                "duration_minutes": max(6, total_minutes),
                "narrative": narrative,
                "confidence": round(min(confidence, 0.98), 2),
                "evidence_refs": evidence_refs[:20],
            }
        )

    return suggestions
