"""Step pipeline widget showing playbook execution progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class StepPipeline(Static):
    """Shows playbook steps and their execution status."""

    DEFAULT_CSS = """
    StepPipeline {
        height: auto;
        padding: 1;
    }
    StepPipeline .step-item {
        height: 1;
        margin-bottom: 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._steps: list[dict] = []

    def set_steps(self, steps: list[dict]) -> None:
        self._steps = steps
        self._render_steps()

    def update_step_status(self, step_id: str, status: str) -> None:
        for step in self._steps:
            if step["id"] == step_id:
                step["status"] = status
                break
        self._render_steps()

    def _render_steps(self) -> None:
        icons = {"pending": "\u2502", "running": "\u25b6", "completed": "\u2713", "failed": "\u2717"}
        lines = []
        for step in self._steps:
            icon = icons.get(step.get("status", "pending"), "\u2502")
            lines.append(f" {icon} {step['id']} ({step.get('type', '?')})")
        self.update("\n".join(lines))
