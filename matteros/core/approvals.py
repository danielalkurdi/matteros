from __future__ import annotations

from typing import Protocol

from matteros.core.types import ApprovalDecision, TimeEntrySuggestion


class ApprovalHandler(Protocol):
    def __call__(self, suggestion: TimeEntrySuggestion, index: int) -> ApprovalDecision: ...
