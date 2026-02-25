from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class StepType(str, Enum):
    COLLECT = "collect"
    TRANSFORM = "transform"
    LLM = "llm"
    APPROVE = "approve"
    APPLY = "apply"


class PermissionMode(str, Enum):
    READ = "read"
    WRITE = "write"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING_APPROVAL = "pending_approval"


class PlaybookMetadata(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0"


class PlaybookStep(BaseModel):
    id: str
    type: StepType
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class PlaybookDefinition(BaseModel):
    metadata: PlaybookMetadata
    connectors: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlaybookStep]

    @model_validator(mode="after")
    def validate_steps(self) -> "PlaybookDefinition":
        if not self.steps:
            raise ValueError("playbook must define at least one step")

        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("playbook contains duplicate step ids")

        return self


class ConnectorManifest(BaseModel):
    connector_id: str
    description: str
    default_mode: PermissionMode = PermissionMode.READ
    operations: dict[str, PermissionMode] = Field(default_factory=dict)


class StepResult(BaseModel):
    step_id: str
    status: str
    output: Any = None
    error: str | None = None


class TimeEntrySuggestion(BaseModel):
    matter_id: str
    client_id: str | None = None
    duration_minutes: int
    narrative: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    decision: str
    reason: str | None = None
    edited_entry: TimeEntrySuggestion | None = None


class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    step_results: list[StepResult]
    outputs: dict[str, Any] = Field(default_factory=dict)
