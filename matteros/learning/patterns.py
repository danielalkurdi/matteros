"""Pattern learning engine that analyzes approval/rejection history."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from matteros.core.store import SQLiteStore


class PatternEngine:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def learn_from_approvals(self, run_id: str) -> list[dict]:
        """Load all approvals for a run, analyze patterns, and store them.

        Returns:
            List of newly learned pattern dicts.
        """
        with self.store.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, decision, reason, entry_json
                FROM approvals
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()

        approved: list[dict] = []
        rejected: list[dict] = []
        for row in rows:
            entry = json.loads(row["entry_json"]) if row["entry_json"] else {}
            record = {
                "id": row["id"],
                "decision": row["decision"],
                "reason": row["reason"],
                "entry": entry,
            }
            if row["decision"] == "approve":
                approved.append(record)
            elif row["decision"] == "reject":
                rejected.append(record)

        patterns: list[dict] = []
        patterns.extend(self._analyze_matter_patterns(approved))
        patterns.extend(self._analyze_duration_patterns(approved))
        patterns.extend(self._analyze_narrative_patterns(approved))
        patterns.extend(self._analyze_rejection_patterns(rejected))
        return patterns

    def apply_patterns(self, suggestions: list[dict]) -> list[dict]:
        """Load all patterns and apply matching ones to modify suggestions.

        Returns:
            Modified suggestions with confidence adjustments.
        """
        patterns = self.get_patterns()
        if not patterns:
            return suggestions

        by_type: dict[str, list[dict]] = defaultdict(list)
        for p in patterns:
            rule = p.get("rule", {})
            by_type[rule.get("type", "")].append(p)

        result: list[dict] = []
        for suggestion in suggestions:
            s = dict(suggestion)
            s = self._apply_matter_assignment(s, by_type.get("matter_assignment", []))
            s = self._apply_duration_correction(s, by_type.get("duration_correction", []))
            s = self._apply_narrative_preference(s, by_type.get("narrative_preference", []))
            s = self._apply_rejection_rules(s, by_type.get("rejection_rule", []))
            result.append(s)

        return result

    def get_patterns(
        self,
        matter_id: str | None = None,
        pattern_type: str | None = None,
    ) -> list[dict]:
        """Query patterns table with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if matter_id is not None:
            clauses.append("matter_id = ?")
            params.append(matter_id)
        if pattern_type is not None:
            clauses.append("pattern_type = ?")
            params.append(pattern_type)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.store.connection() as conn:
            rows = conn.execute(
                f"SELECT id, pattern_type, matter_id, rule_json, confidence, sample_count, created_at, updated_at FROM patterns{where}",  # noqa: S608
                params,
            ).fetchall()

        return [
            {
                "id": row["id"],
                "pattern_type": row["pattern_type"],
                "matter_id": row["matter_id"],
                "rule": json.loads(row["rule_json"]) if row["rule_json"] else {},
                "confidence": row["confidence"],
                "sample_count": row["sample_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Internal analysis helpers
    # ------------------------------------------------------------------

    def _analyze_matter_patterns(self, approvals: list[dict]) -> list[dict]:
        """Group approved entries by matter_id and look for keyword patterns."""
        by_matter: dict[str, list[dict]] = defaultdict(list)
        for a in approvals:
            mid = a["entry"].get("matter_id", "UNASSIGNED")
            if mid != "UNASSIGNED":
                by_matter[mid].append(a)

        patterns: list[dict] = []
        for matter_id, items in by_matter.items():
            keywords = self._extract_keywords(items)
            if not keywords:
                continue
            for kw in keywords:
                rule = {
                    "type": "matter_assignment",
                    "condition": {"keyword": kw, "source": "narrative"},
                    "action": {"matter_id": matter_id},
                    "confidence": min(0.95, 0.5 + 0.1 * len(items)),
                    "sample_count": len(items),
                }
                patterns.append(self._store_pattern("matter_assignment", matter_id, rule))
        return patterns

    def _analyze_duration_patterns(self, approvals: list[dict]) -> list[dict]:
        """Compare original vs approved duration for consistent corrections."""
        corrections: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for a in approvals:
            entry = a["entry"]
            original = entry.get("original_duration_minutes")
            approved = entry.get("duration_minutes")
            if original is not None and approved is not None and original != approved:
                mid = entry.get("matter_id", "UNASSIGNED")
                corrections[mid].append((int(original), int(approved)))

        patterns: list[dict] = []
        for matter_id, pairs in corrections.items():
            if len(pairs) < 2:
                continue
            ratios = [approved / original for original, approved in pairs if original > 0]
            if not ratios:
                continue
            avg_ratio = sum(ratios) / max(len(ratios), 1)
            spread = max(ratios) - min(ratios)
            if spread < 0.15:
                rule = {
                    "type": "duration_correction",
                    "condition": {"matter_id": matter_id},
                    "action": {"multiply_by": round(avg_ratio, 3)},
                    "confidence": min(0.95, 0.5 + 0.1 * len(pairs)),
                    "sample_count": len(pairs),
                }
                patterns.append(self._store_pattern("duration_correction", matter_id, rule))
        return patterns

    def _analyze_narrative_patterns(self, approvals: list[dict]) -> list[dict]:
        """Analyze approved narratives for common prefixes/formats."""
        by_matter: dict[str, list[str]] = defaultdict(list)
        for a in approvals:
            narrative = a["entry"].get("narrative", "")
            mid = a["entry"].get("matter_id", "UNASSIGNED")
            if narrative:
                by_matter[mid].append(narrative)

        patterns: list[dict] = []
        for matter_id, narratives in by_matter.items():
            if len(narratives) < 2:
                continue
            prefix = _common_prefix(narratives)
            if len(prefix) >= 8:
                rule = {
                    "type": "narrative_preference",
                    "condition": {"matter_id": matter_id},
                    "action": {"preferred_prefix": prefix.strip()},
                    "confidence": min(0.90, 0.5 + 0.1 * len(narratives)),
                    "sample_count": len(narratives),
                }
                patterns.append(self._store_pattern("narrative_preference", matter_id, rule))
        return patterns

    def _analyze_rejection_patterns(self, rejected: list[dict]) -> list[dict]:
        """Look for common attributes in rejected entries."""
        by_matter: dict[str, list[dict]] = defaultdict(list)
        for r in rejected:
            mid = r["entry"].get("matter_id", "UNASSIGNED")
            by_matter[mid].append(r)

        patterns: list[dict] = []
        for matter_id, items in by_matter.items():
            if len(items) < 2:
                continue
            durations = [item["entry"].get("duration_minutes", 0) for item in items]
            max_dur = max(durations) if durations else 0
            if max_dur > 0 and max_dur <= 6:
                rule = {
                    "type": "rejection_rule",
                    "condition": {"matter_id": matter_id, "max_duration_minutes": max_dur},
                    "action": {"reject": True},
                    "confidence": min(0.90, 0.5 + 0.1 * len(items)),
                    "sample_count": len(items),
                }
                patterns.append(self._store_pattern("rejection_rule", matter_id, rule))
        return patterns

    # ------------------------------------------------------------------
    # Pattern application helpers
    # ------------------------------------------------------------------

    def _apply_matter_assignment(
        self, suggestion: dict, patterns: list[dict]
    ) -> dict:
        if suggestion.get("matter_id") != "UNASSIGNED":
            return suggestion
        narrative = suggestion.get("narrative", "").lower()
        best: dict | None = None
        best_conf = 0.0
        for p in patterns:
            rule = p.get("rule", {})
            kw = rule.get("condition", {}).get("keyword", "").lower()
            if kw and kw in narrative:
                conf = float(rule.get("confidence", 0))
                if conf > best_conf:
                    best = rule
                    best_conf = conf
        if best:
            suggestion["matter_id"] = best["action"]["matter_id"]
            suggestion["confidence"] = round(
                min(1.0, suggestion.get("confidence", 0.5) + 0.1), 2
            )
        return suggestion

    def _apply_duration_correction(
        self, suggestion: dict, patterns: list[dict]
    ) -> dict:
        mid = suggestion.get("matter_id", "")
        for p in patterns:
            rule = p.get("rule", {})
            if rule.get("condition", {}).get("matter_id") == mid:
                multiplier = float(rule.get("action", {}).get("multiply_by", 1.0))
                original = int(suggestion.get("duration_minutes", 0))
                suggestion["duration_minutes"] = max(1, round(original * multiplier))
                break
        return suggestion

    def _apply_narrative_preference(
        self, suggestion: dict, patterns: list[dict]
    ) -> dict:
        mid = suggestion.get("matter_id", "")
        for p in patterns:
            rule = p.get("rule", {})
            if rule.get("condition", {}).get("matter_id") == mid:
                prefix = rule.get("action", {}).get("preferred_prefix", "")
                if prefix and not suggestion.get("narrative", "").startswith(prefix):
                    suggestion["narrative"] = f"{prefix} {suggestion.get('narrative', '')}"
                break
        return suggestion

    def _apply_rejection_rules(
        self, suggestion: dict, patterns: list[dict]
    ) -> dict:
        mid = suggestion.get("matter_id", "")
        dur = int(suggestion.get("duration_minutes", 0))
        for p in patterns:
            rule = p.get("rule", {})
            cond = rule.get("condition", {})
            if cond.get("matter_id") == mid:
                max_dur = int(cond.get("max_duration_minutes", 0))
                if 0 < dur <= max_dur:
                    suggestion["confidence"] = round(
                        max(0.0, suggestion.get("confidence", 0.5) - 0.3), 2
                    )
                    suggestion["rejection_risk"] = True
                    break
        return suggestion

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _store_pattern(
        self, pattern_type: str, matter_id: str, rule: dict
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        confidence = float(rule.get("confidence", 0.5))
        sample_count = int(rule.get("sample_count", 0))

        with self.store.connection() as conn:
            # Dedup: update existing pattern with same type + matter_id.
            existing = conn.execute(
                "SELECT id FROM patterns WHERE pattern_type = ? AND matter_id = ?",
                (pattern_type, matter_id),
            ).fetchone()

            if existing:
                pattern_id = existing["id"]
                conn.execute(
                    """
                    UPDATE patterns
                    SET rule_json = ?, confidence = ?, sample_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (json.dumps(rule), confidence, sample_count, now, pattern_id),
                )
            else:
                pattern_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO patterns (id, pattern_type, matter_id, rule_json, confidence, sample_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pattern_id,
                        pattern_type,
                        matter_id,
                        json.dumps(rule),
                        confidence,
                        sample_count,
                        now,
                        now,
                    ),
                )
            conn.commit()

        return {
            "id": pattern_id,
            "pattern_type": pattern_type,
            "matter_id": matter_id,
            "rule": rule,
            "confidence": confidence,
            "sample_count": sample_count,
            "created_at": now,
            "updated_at": now,
        }

    def _extract_keywords(self, items: list[dict]) -> list[str]:
        """Extract recurring keywords from entry narratives."""
        word_counts: dict[str, int] = defaultdict(int)
        for item in items:
            narrative = item.get("entry", {}).get("narrative", "")
            for word in narrative.lower().split():
                cleaned = word.strip(".,;:!?()[]\"'")
                if len(cleaned) >= 4:
                    word_counts[cleaned] += 1

        threshold = max(2, max(len(items), 1) // 2)
        return [w for w, c in word_counts.items() if c >= threshold]


def _common_prefix(strings: list[str]) -> str:
    """Return the longest common prefix of a list of strings."""
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix
