"""Live event log widget that subscribes to the EventBus."""

from __future__ import annotations

from textual.widgets import RichLog


class EventLog(RichLog):
    """A RichLog that formats RunEvents for display."""

    def append_event(self, event_type: str, step_id: str | None, data: dict) -> None:
        step_label = f" [{step_id}]" if step_id else ""
        self.write(f"[bold]{event_type}[/bold]{step_label}")
        for key, value in data.items():
            self.write(f"  {key}: {value}")
