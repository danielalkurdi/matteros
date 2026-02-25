"""Tests for the learning/patterns module."""

from __future__ import annotations

import json
from pathlib import Path

from matteros.core.store import SQLiteStore
from matteros.learning.patterns import PatternEngine, _common_prefix


# -- _common_prefix -----------------------------------------------------------


def test_common_prefix_empty_list() -> None:
    assert _common_prefix([]) == ""


def test_common_prefix_single_string() -> None:
    assert _common_prefix(["hello world"]) == "hello world"


def test_common_prefix_no_common() -> None:
    assert _common_prefix(["abc", "xyz"]) == ""


def test_common_prefix_full_match() -> None:
    assert _common_prefix(["same", "same"]) == "same"


def test_common_prefix_partial() -> None:
    assert _common_prefix(["Matter 100: review", "Matter 100: draft"]) == "Matter 100: "


# -- _extract_keywords --------------------------------------------------------


def _make_engine(tmp_path: Path) -> PatternEngine:
    store = SQLiteStore(tmp_path / "test.db")
    return PatternEngine(store)


def test_extract_keywords_basic(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    items = [
        {"entry": {"narrative": "Reviewed compliance documents for client"}},
        {"entry": {"narrative": "Reviewed compliance filing updates"}},
        {"entry": {"narrative": "Reviewed compliance memo draft"}},
    ]
    keywords = engine._extract_keywords(items)
    assert "reviewed" in keywords
    assert "compliance" in keywords


def test_extract_keywords_short_words_filtered(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    items = [
        {"entry": {"narrative": "the big red fox"}},
        {"entry": {"narrative": "the big red car"}},
    ]
    keywords = engine._extract_keywords(items)
    # "the", "big", "red" are all < 4 chars
    assert "the" not in keywords
    assert "big" not in keywords
    assert "red" not in keywords


def test_extract_keywords_threshold(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    # With 4 items, threshold = max(2, 4//2) = 2
    items = [
        {"entry": {"narrative": "review contract alpha"}},
        {"entry": {"narrative": "review contract beta"}},
        {"entry": {"narrative": "draft memo gamma"}},
        {"entry": {"narrative": "draft memo delta"}},
    ]
    keywords = engine._extract_keywords(items)
    assert "review" in keywords
    assert "contract" in keywords
    assert "draft" in keywords
    assert "memo" in keywords


# -- _analyze_matter_patterns -------------------------------------------------


def test_analyze_matter_patterns(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "narrative": "Reviewed compliance docs"}},
        {"entry": {"matter_id": "MAT-100", "narrative": "Reviewed compliance filing"}},
        {"entry": {"matter_id": "MAT-100", "narrative": "Reviewed compliance memo"}},
    ]
    patterns = engine._analyze_matter_patterns(approvals)
    assert len(patterns) > 0
    assert patterns[0]["pattern_type"] == "matter_assignment"
    assert patterns[0]["matter_id"] == "MAT-100"


def test_analyze_matter_patterns_skips_unassigned(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "UNASSIGNED", "narrative": "Some work"}},
        {"entry": {"matter_id": "UNASSIGNED", "narrative": "Some work again"}},
    ]
    patterns = engine._analyze_matter_patterns(approvals)
    assert patterns == []


# -- _analyze_duration_patterns -----------------------------------------------


def test_analyze_duration_patterns(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "original_duration_minutes": 30, "duration_minutes": 45}},
        {"entry": {"matter_id": "MAT-100", "original_duration_minutes": 20, "duration_minutes": 30}},
    ]
    patterns = engine._analyze_duration_patterns(approvals)
    assert len(patterns) == 1
    assert patterns[0]["pattern_type"] == "duration_correction"
    rule = patterns[0]["rule"]
    assert 1.4 <= rule["action"]["multiply_by"] <= 1.6


def test_analyze_duration_patterns_spread_too_wide(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "original_duration_minutes": 30, "duration_minutes": 60}},
        {"entry": {"matter_id": "MAT-100", "original_duration_minutes": 30, "duration_minutes": 15}},
    ]
    patterns = engine._analyze_duration_patterns(approvals)
    assert patterns == []  # spread too wide


def test_analyze_duration_patterns_needs_two_pairs(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "original_duration_minutes": 30, "duration_minutes": 45}},
    ]
    patterns = engine._analyze_duration_patterns(approvals)
    assert patterns == []


# -- _analyze_narrative_patterns ----------------------------------------------


def test_analyze_narrative_patterns(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "narrative": "PRIVILEGED: Review of contract terms"}},
        {"entry": {"matter_id": "MAT-100", "narrative": "PRIVILEGED: Draft response letter"}},
    ]
    patterns = engine._analyze_narrative_patterns(approvals)
    assert len(patterns) == 1
    assert patterns[0]["rule"]["action"]["preferred_prefix"] == "PRIVILEGED:"


def test_analyze_narrative_patterns_prefix_too_short(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "narrative": "Re: abc"}},
        {"entry": {"matter_id": "MAT-100", "narrative": "Re: xyz"}},
    ]
    patterns = engine._analyze_narrative_patterns(approvals)
    assert patterns == []  # "Re: " is only 4 chars


def test_analyze_narrative_patterns_needs_two(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    approvals = [
        {"entry": {"matter_id": "MAT-100", "narrative": "PRIVILEGED: only one"}},
    ]
    patterns = engine._analyze_narrative_patterns(approvals)
    assert patterns == []


# -- _analyze_rejection_patterns ----------------------------------------------


def test_analyze_rejection_patterns(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    rejected = [
        {"entry": {"matter_id": "MAT-100", "duration_minutes": 3}},
        {"entry": {"matter_id": "MAT-100", "duration_minutes": 5}},
    ]
    patterns = engine._analyze_rejection_patterns(rejected)
    assert len(patterns) == 1
    assert patterns[0]["rule"]["condition"]["max_duration_minutes"] == 5


def test_analyze_rejection_patterns_needs_two(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    rejected = [{"entry": {"matter_id": "MAT-100", "duration_minutes": 3}}]
    patterns = engine._analyze_rejection_patterns(rejected)
    assert patterns == []


# -- _apply_matter_assignment -------------------------------------------------


def test_apply_matter_assignment_unassigned_only(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "UNASSIGNED", "narrative": "compliance review", "confidence": 0.5}
    patterns = [
        {
            "rule": {
                "type": "matter_assignment",
                "condition": {"keyword": "compliance", "source": "narrative"},
                "action": {"matter_id": "MAT-100"},
                "confidence": 0.8,
            }
        }
    ]
    result = engine._apply_matter_assignment(suggestion, patterns)
    assert result["matter_id"] == "MAT-100"
    assert result["confidence"] == 0.6  # 0.5 + 0.1


def test_apply_matter_assignment_already_assigned(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-200", "narrative": "compliance review", "confidence": 0.5}
    patterns = [
        {
            "rule": {
                "type": "matter_assignment",
                "condition": {"keyword": "compliance"},
                "action": {"matter_id": "MAT-100"},
                "confidence": 0.8,
            }
        }
    ]
    result = engine._apply_matter_assignment(suggestion, patterns)
    assert result["matter_id"] == "MAT-200"  # unchanged


def test_apply_matter_assignment_best_confidence(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "UNASSIGNED", "narrative": "compliance review", "confidence": 0.5}
    patterns = [
        {"rule": {"condition": {"keyword": "compliance"}, "action": {"matter_id": "MAT-100"}, "confidence": 0.6}},
        {"rule": {"condition": {"keyword": "review"}, "action": {"matter_id": "MAT-200"}, "confidence": 0.9}},
    ]
    result = engine._apply_matter_assignment(suggestion, patterns)
    assert result["matter_id"] == "MAT-200"  # higher confidence wins


# -- _apply_duration_correction -----------------------------------------------


def test_apply_duration_correction(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-100", "duration_minutes": 30}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100"}, "action": {"multiply_by": 1.5}}}
    ]
    result = engine._apply_duration_correction(suggestion, patterns)
    assert result["duration_minutes"] == 45


def test_apply_duration_correction_no_match(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-200", "duration_minutes": 30}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100"}, "action": {"multiply_by": 1.5}}}
    ]
    result = engine._apply_duration_correction(suggestion, patterns)
    assert result["duration_minutes"] == 30  # unchanged


# -- _apply_narrative_preference ----------------------------------------------


def test_apply_narrative_preference(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-100", "narrative": "Review of documents"}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100"}, "action": {"preferred_prefix": "PRIVILEGED:"}}}
    ]
    result = engine._apply_narrative_preference(suggestion, patterns)
    assert result["narrative"].startswith("PRIVILEGED:")


def test_apply_narrative_preference_already_prefixed(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-100", "narrative": "PRIVILEGED: Review of documents"}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100"}, "action": {"preferred_prefix": "PRIVILEGED:"}}}
    ]
    result = engine._apply_narrative_preference(suggestion, patterns)
    assert result["narrative"] == "PRIVILEGED: Review of documents"  # not doubled


# -- _apply_rejection_rules ---------------------------------------------------


def test_apply_rejection_rules(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-100", "duration_minutes": 5, "confidence": 0.7}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100", "max_duration_minutes": 6}, "action": {"reject": True}}}
    ]
    result = engine._apply_rejection_rules(suggestion, patterns)
    assert result["confidence"] == 0.4  # 0.7 - 0.3
    assert result["rejection_risk"] is True


def test_apply_rejection_rules_duration_above_threshold(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    suggestion = {"matter_id": "MAT-100", "duration_minutes": 30, "confidence": 0.7}
    patterns = [
        {"rule": {"condition": {"matter_id": "MAT-100", "max_duration_minutes": 6}, "action": {"reject": True}}}
    ]
    result = engine._apply_rejection_rules(suggestion, patterns)
    assert result["confidence"] == 0.7  # unchanged
    assert "rejection_risk" not in result


# -- learn_from_approvals end-to-end ------------------------------------------


def test_learn_from_approvals(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db")
    engine = PatternEngine(store)

    # Seed a parent run and approval rows
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, playbook_name, status, started_at, dry_run, approve_mode, input_json) "
            "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
            ("run-1", "test.yml", "completed", 0, 0, "{}"),
        )
        for i in range(3):
            entry = {
                "matter_id": "MAT-100",
                "duration_minutes": 30,
                "narrative": f"Reviewed compliance document #{i}",
            }
            conn.execute(
                "INSERT INTO approvals (id, run_id, step_id, item_index, decision, reason, entry_json, reviewer, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (f"a-{i}", "run-1", "step-1", i, "approve", None, json.dumps(entry), "tester"),
            )
        conn.commit()

    patterns = engine.learn_from_approvals("run-1")
    assert len(patterns) > 0
    types = {p["pattern_type"] for p in patterns}
    assert "matter_assignment" in types
