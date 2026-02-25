"""Audit screen: browse and filter audit events with syntax-highlighted JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label, Static

from matteros.core.store import SQLiteStore


class AuditScreen(Screen):
    """Filterable audit event browser."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("f", "focus_filter", "Filter"),
        ("/", "focus_filter", "Filter"),
    ]

    DEFAULT_CSS = """
    AuditScreen #filter-bar {
        height: 3;
        padding: 0 1;
        border-bottom: tall $accent;
    }
    AuditScreen #table-area {
        height: 1fr;
    }
    AuditScreen #detail-panel {
        height: 40%;
        border-top: tall $accent;
        padding: 1;
        overflow-y: auto;
    }
    """

    def __init__(self, home: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.home = home
        self._events: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="filter-bar"):
                yield Label("Filter: ")
                yield Input(placeholder="event type, run id, or step id...", id="filter-input")
            yield DataTable(id="audit-table")
            with Vertical(id="detail-panel"):
                yield Static("Select an event to view details", id="detail-content")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.add_columns("Seq", "Run ID", "Timestamp", "Type", "Actor", "Step")
        table.cursor_type = "row"
        self._load_events()

    def _load_events(self, filter_text: str = "") -> None:
        store = SQLiteStore(self.home / "matteros.db")
        self._events = store.list_audit_events(limit=200)
        self._events.reverse()

        table = self.query_one("#audit-table", DataTable)
        table.clear()

        for event in self._events:
            if filter_text:
                searchable = f"{event.get('event_type', '')} {event.get('run_id', '')} {event.get('step_id', '')}"
                if filter_text.lower() not in searchable.lower():
                    continue
            table.add_row(
                str(event.get("seq", "")),
                str(event.get("run_id", ""))[:8],
                str(event.get("timestamp", ""))[:19],
                str(event.get("event_type", "")),
                str(event.get("actor", "")),
                str(event.get("step_id", "") or "-"),
                key=str(event.get("seq", "")),
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._load_events(event.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None:
            return
        seq = str(event.row_key.value)
        for ev in self._events:
            if str(ev.get("seq")) == seq:
                detail = self.query_one("#detail-content", Static)
                formatted = json.dumps(ev.get("data", {}), indent=2, sort_keys=True)
                detail.update(
                    f"[bold]Event #{seq}[/bold]\n"
                    f"Run: {ev.get('run_id', '')}\n"
                    f"Type: {ev.get('event_type', '')}\n"
                    f"Hash: {ev.get('event_hash', '')[:16]}...\n\n"
                    f"[bold]Data:[/bold]\n{formatted}"
                )
                break

    def action_focus_filter(self) -> None:
        self.query_one("#filter-input", Input).focus()
