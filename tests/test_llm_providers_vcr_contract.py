from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

import pytest

from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1, normalize_named_schema
from matteros.llm.providers.anthropic import AnthropicProvider
from matteros.llm.providers.openai import OpenAIProvider

pytestmark = pytest.mark.external

CASSETTE_DIR = Path(__file__).resolve().parent / "cassettes"


@pytest.fixture(scope="module")
def recorder():
    if find_spec("vcr") is None:
        pytest.skip("vcrpy is not installed (install dev dependencies with vcrpy)")
    import vcr

    record_mode = os.getenv("MATTEROS_VCR_RECORD_MODE", "none").strip().lower()
    return vcr.VCR(
        cassette_library_dir=str(CASSETTE_DIR),
        record_mode=record_mode,
        filter_headers=[("authorization", "REDACTED"), ("x-api-key", "REDACTED")],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )


def _external_enabled() -> bool:
    value = os.getenv("MATTEROS_RUN_EXTERNAL_TESTS", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _require_external_and_cassette(cassette_name: str) -> None:
    if not _external_enabled():
        pytest.skip("set MATTEROS_RUN_EXTERNAL_TESTS=1 to run external provider contract tests")

    record_mode = os.getenv("MATTEROS_VCR_RECORD_MODE", "none").strip().lower()
    cassette_path = CASSETTE_DIR / cassette_name
    if record_mode == "none" and not cassette_path.exists():
        pytest.skip(
            "cassette missing in replay mode; set MATTEROS_VCR_RECORD_MODE=once with API key to record"
        )


def _sample_payload() -> dict:
    return {
        "clusters": [
            {
                "matter_id": "MAT-123",
                "activity_count": 2,
                "activity_types": ["calendar", "email"],
                "total_minutes": 30,
                "activities": [
                    {
                        "kind": "calendar",
                        "title": "MAT-123 status call",
                        "duration_minutes": 24,
                        "timestamp": "2026-02-20T09:00:00Z",
                        "matter_id": "MAT-123",
                        "evidence_ref": "cal-1",
                    },
                    {
                        "kind": "email",
                        "title": "Re: MAT-123 docs",
                        "duration_minutes": 6,
                        "timestamp": "2026-02-20T09:45:00Z",
                        "matter_id": "MAT-123",
                        "evidence_ref": "mail-1",
                    },
                ],
                "evidence_refs": ["cal-1", "mail-1"],
            }
        ]
    }


def test_openai_vcr_contract(recorder) -> None:
    cassette_name = "openai_draft_time_entries.yaml"
    _require_external_and_cassette(cassette_name)

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not configured")

    provider = OpenAIProvider()
    with recorder.use_cassette(cassette_name):
        payload = provider.generate(
            task="draft_time_entries",
            payload=_sample_payload(),
            schema_name=SCHEMA_TIME_ENTRY_V1,
        )

    normalized = normalize_named_schema(SCHEMA_TIME_ENTRY_V1, payload)
    assert normalized["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert isinstance(normalized["suggestions"], list)


def test_anthropic_vcr_contract(recorder) -> None:
    cassette_name = "anthropic_draft_time_entries.yaml"
    _require_external_and_cassette(cassette_name)

    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not configured")

    provider = AnthropicProvider()
    with recorder.use_cassette(cassette_name):
        payload = provider.generate(
            task="draft_time_entries",
            payload=_sample_payload(),
            schema_name=SCHEMA_TIME_ENTRY_V1,
        )

    normalized = normalize_named_schema(SCHEMA_TIME_ENTRY_V1, payload)
    assert normalized["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert isinstance(normalized["suggestions"], list)
