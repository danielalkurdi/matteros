"""Tests for the narrative_polish skill."""

from __future__ import annotations

from matteros.skills.narrative_polish import narrative_polish


def test_capitalizes_and_deduplicates() -> None:
    result = narrative_polish({"narrative": "hello hello world. the the end."})
    text = result["polished_narrative"]
    assert text.startswith("Hello")
    assert "hello hello" not in text.lower()
    assert "the the" not in text.lower()


def test_trims_evidence_refs() -> None:
    result = narrative_polish({"narrative": "Reviewed document [ref:abc123] and filed."})
    text = result["polished_narrative"]
    assert "[ref:" not in text
    assert "Reviewed" in text
    assert "filed" in text
