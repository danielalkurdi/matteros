from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SchemaValidationError(ValueError):
    """Raised when a named schema payload is invalid."""


class TimeEntrySuggestionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter_id: str
    client_id: str | None = None
    duration_minutes: int = Field(gt=0)
    narrative: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class TimeEntrySuggestionsV1Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["time_entry_suggestions.v1"]
    suggestions: list[TimeEntrySuggestionV1]


class LegacyEntryV0(BaseModel):
    model_config = ConfigDict(extra="allow")

    matter: str | None = None
    matter_id: str | None = None
    minutes: int | None = None
    duration_minutes: int | None = None
    description: str | None = None
    narrative: str | None = None
    confidence: float | None = None
    evidence: list[str] | None = None
    evidence_refs: list[str] | None = None
    client: str | None = None
    client_id: str | None = None


class LegacyTimeEntryEnvelopeV0(BaseModel):
    model_config = ConfigDict(extra="allow")

    entries: list[LegacyEntryV0] = Field(default_factory=list)


SCHEMA_TIME_ENTRY_V1 = "time_entry_suggestions.v1"


def normalize_named_schema(schema_name: str, payload: Any) -> dict[str, Any]:
    if schema_name != SCHEMA_TIME_ENTRY_V1:
        raise SchemaValidationError(f"unsupported schema name: {schema_name}")

    if not isinstance(payload, dict):
        raise SchemaValidationError("schema payload must be an object")

    migrated = _migrate_time_entry_payload(payload)
    envelope = TimeEntrySuggestionsV1Envelope.model_validate(migrated)
    return envelope.model_dump(mode="json")


def schema_json(schema_name: str) -> dict[str, Any]:
    if schema_name != SCHEMA_TIME_ENTRY_V1:
        raise SchemaValidationError(f"unsupported schema name: {schema_name}")
    return TimeEntrySuggestionsV1Envelope.model_json_schema()


def _migrate_time_entry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = payload.get("schema_version")
    if schema_version == SCHEMA_TIME_ENTRY_V1:
        return payload

    if "entries" in payload:
        legacy = LegacyTimeEntryEnvelopeV0.model_validate(payload)
        suggestions: list[dict[str, Any]] = []
        for entry in legacy.entries:
            matter_id = entry.matter_id or entry.matter or "UNASSIGNED"
            duration_minutes = entry.duration_minutes or entry.minutes or 6
            narrative = entry.narrative or entry.description or f"Matter {matter_id} legal work"
            confidence = 0.5 if entry.confidence is None else float(entry.confidence)
            evidence_refs = entry.evidence_refs or entry.evidence or []
            client_id = entry.client_id or entry.client
            suggestions.append(
                {
                    "matter_id": matter_id,
                    "client_id": client_id,
                    "duration_minutes": duration_minutes,
                    "narrative": narrative,
                    "confidence": confidence,
                    "evidence_refs": evidence_refs,
                }
            )
        return {
            "schema_version": SCHEMA_TIME_ENTRY_V1,
            "suggestions": suggestions,
        }

    if "suggestions" in payload:
        # Transitional payloads without explicit schema_version are upgraded to v1.
        return {
            "schema_version": SCHEMA_TIME_ENTRY_V1,
            "suggestions": payload.get("suggestions", []),
        }

    raise SchemaValidationError(
        "payload does not match known time entry schema versions (expected suggestions or entries)"
    )
