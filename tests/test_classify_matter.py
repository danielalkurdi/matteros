"""Tests for the classify_matter skill."""

from __future__ import annotations

from matteros.skills.classify_matter import classify_matter


def test_returns_matter_id_with_confidence() -> None:
    result = classify_matter({"texts": ["Working on MAT-1234 today"]})
    assert result["matter_id"] != "UNASSIGNED"
    assert result["confidence"] == 0.9


def test_returns_unassigned_with_low_confidence() -> None:
    result = classify_matter({"texts": ["Just a regular meeting"]})
    assert result["matter_id"] == "UNASSIGNED"
    assert result["confidence"] == 0.1
