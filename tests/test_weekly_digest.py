"""Tests for the weekly_digest skill."""

from __future__ import annotations

from matteros.skills.weekly_digest import weekly_digest


def test_markdown_output_from_sample_entries() -> None:
    entries = [
        {"matter_id": "MAT-1", "duration_minutes": 30},
        {"matter_id": "MAT-1", "duration_minutes": 15},
        {"matter_id": "MAT-2", "duration_minutes": 60},
    ]
    result = weekly_digest({"entries": entries})
    md = result["markdown"]
    assert "MAT-1" in md
    assert "MAT-2" in md
    assert "45" in md  # MAT-1 total
    assert "60" in md  # MAT-2 total
    assert "|" in md


def test_empty_entries_returns_empty_table() -> None:
    result = weekly_digest({"entries": []})
    md = result["markdown"]
    assert "Matter" in md
    assert "Total Minutes" in md
