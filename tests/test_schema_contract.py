from __future__ import annotations

import pytest

from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1, normalize_named_schema, schema_json


def test_schema_contract_accepts_v1_payload() -> None:
    payload = {
        "schema_version": SCHEMA_TIME_ENTRY_V1,
        "suggestions": [
            {
                "matter_id": "MAT-123",
                "client_id": None,
                "duration_minutes": 30,
                "narrative": "Matter MAT-123 update",
                "confidence": 0.8,
                "evidence_refs": ["mail-1"],
            }
        ],
    }

    normalized = normalize_named_schema(SCHEMA_TIME_ENTRY_V1, payload)
    assert normalized["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert len(normalized["suggestions"]) == 1


def test_schema_contract_migrates_legacy_entries_payload() -> None:
    payload = {
        "entries": [
            {
                "matter": "MAT-777",
                "minutes": 24,
                "description": "Legacy format narrative",
                "confidence": 0.65,
                "evidence": ["cal-1"],
            }
        ]
    }

    normalized = normalize_named_schema(SCHEMA_TIME_ENTRY_V1, payload)
    entry = normalized["suggestions"][0]
    assert normalized["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert entry["matter_id"] == "MAT-777"
    assert entry["duration_minutes"] == 24
    assert entry["narrative"] == "Legacy format narrative"


def test_schema_contract_rejects_invalid_payload() -> None:
    payload = {
        "schema_version": SCHEMA_TIME_ENTRY_V1,
        "suggestions": [{"matter_id": "X"}],
    }

    with pytest.raises(Exception):
        normalize_named_schema(SCHEMA_TIME_ENTRY_V1, payload)


def test_schema_json_exports_contract() -> None:
    schema = schema_json(SCHEMA_TIME_ENTRY_V1)
    assert schema["type"] == "object"
    assert "properties" in schema
