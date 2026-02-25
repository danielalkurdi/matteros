"""Approval screen: review and approve/reject time entry suggestions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label, Static

from matteros.core.store import SQLiteStore
from matteros.core.types import ApprovalDecision, TimeEntrySuggestion


class ApprovalScreen(Screen):
    """Interactive approval queue for time entry suggestions."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("a", "approve_selected", "Approve"),
        ("r", "reject_selected", "Reject"),
        ("e", "edit_selected", "Edit"),
        ("A", "approve_all", "Approve All"),
    ]

    DEFAULT_CSS = """
    ApprovalScreen #table-container {
        height: 1fr;
    }
    ApprovalScreen #detail-panel {
        height: auto;
        max-height: 40%;
        border-top: tall $accent;
        padding: 1;
    }
    ApprovalScreen #status-bar {
        height: 1;
        dock: bottom;
        background: $accent;
        padding: 0 1;
    }
    """

    def __init__(self, suggestions: list[dict[str, Any]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._suggestions = [TimeEntrySuggestion.model_validate(s) for s in suggestions]
        self._decisions: dict[int, ApprovalDecision] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="table-container"):
            yield DataTable(id="approval-table")
        with Vertical(id="detail-panel"):
            yield Label("[bold]Detail[/bold]", id="detail-label")
            yield Static("Select an entry to view details", id="detail-content")
        yield Static(
            f"{len(self._suggestions)} entries pending | a=approve r=reject e=edit A=approve all",
            id="status-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#approval-table", DataTable)
        table.add_columns("Idx", "Matter", "Duration", "Confidence", "Status", "Narrative")
        for i, suggestion in enumerate(self._suggestions):
            table.add_row(
                str(i),
                suggestion.matter_id,
                f"{suggestion.duration_minutes}m",
                f"{suggestion.confidence:.0%}",
                "pending",
                suggestion.narrative[:60],
                key=str(i),
            )
        table.cursor_type = "row"

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            idx = int(str(event.row_key.value))
            if 0 <= idx < len(self._suggestions):
                suggestion = self._suggestions[idx]
                detail = self.query_one("#detail-content", Static)
                detail.update(
                    f"[bold]Matter:[/bold] {suggestion.matter_id}\n"
                    f"[bold]Duration:[/bold] {suggestion.duration_minutes}m\n"
                    f"[bold]Confidence:[/bold] {suggestion.confidence:.0%}\n"
                    f"[bold]Evidence:[/bold] {', '.join(suggestion.evidence_refs[:5])}\n"
                    f"[bold]Narrative:[/bold]\n{suggestion.narrative}"
                )

    def action_approve_selected(self) -> None:
        table = self.query_one("#approval-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None and 0 <= row_key < len(self._suggestions):
            self._decisions[row_key] = ApprovalDecision(
                decision="approve",
                edited_entry=self._suggestions[row_key],
            )
            table.update_cell_at((row_key, 4), "[green]approved[/green]")
            self._update_status()

    def action_reject_selected(self) -> None:
        table = self.query_one("#approval-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None and 0 <= row_key < len(self._suggestions):
            self._decisions[row_key] = ApprovalDecision(
                decision="reject",
                reason="rejected via TUI",
            )
            table.update_cell_at((row_key, 4), "[red]rejected[/red]")
            self._update_status()

    def action_edit_selected(self) -> None:
        table = self.query_one("#approval-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None and 0 <= row_key < len(self._suggestions):
            self.app.push_screen(
                EditEntryScreen(self._suggestions[row_key], row_key),
                callback=self._on_edit_complete,
            )

    def action_approve_all(self) -> None:
        table = self.query_one("#approval-table", DataTable)
        for i, suggestion in enumerate(self._suggestions):
            if i not in self._decisions:
                self._decisions[i] = ApprovalDecision(
                    decision="approve",
                    edited_entry=suggestion,
                )
                table.update_cell_at((i, 4), "[green]approved[/green]")
        self._update_status()

    def _on_edit_complete(self, result: tuple[int, TimeEntrySuggestion] | None) -> None:
        if result is None:
            return
        idx, edited = result
        self._suggestions[idx] = edited
        self._decisions[idx] = ApprovalDecision(decision="approve", edited_entry=edited)
        table = self.query_one("#approval-table", DataTable)
        table.update_cell_at((idx, 1), edited.matter_id)
        table.update_cell_at((idx, 2), f"{edited.duration_minutes}m")
        table.update_cell_at((idx, 4), "[green]edited[/green]")
        table.update_cell_at((idx, 5), edited.narrative[:60])
        self._update_status()

    def _update_status(self) -> None:
        approved = sum(1 for d in self._decisions.values() if d.decision == "approve")
        rejected = sum(1 for d in self._decisions.values() if d.decision == "reject")
        pending = len(self._suggestions) - len(self._decisions)
        status = self.query_one("#status-bar", Static)
        status.update(f"Approved: {approved} | Rejected: {rejected} | Pending: {pending}")

    @property
    def decisions(self) -> dict[int, ApprovalDecision]:
        return self._decisions


class EditEntryScreen(Screen):
    """Modal screen for editing a time entry suggestion."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    EditEntryScreen {
        align: center middle;
    }
    EditEntryScreen #edit-container {
        width: 60;
        height: auto;
        border: tall $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, suggestion: TimeEntrySuggestion, index: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._suggestion = suggestion
        self._index = index

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-container"):
            yield Label(f"[bold]Edit Entry #{self._index}[/bold]")
            yield Label("Matter ID:")
            yield Input(value=self._suggestion.matter_id, id="matter-input")
            yield Label("Duration (minutes):")
            yield Input(value=str(self._suggestion.duration_minutes), id="duration-input")
            yield Label("Narrative:")
            yield Input(value=self._suggestion.narrative, id="narrative-input")
            yield Label("\n[dim]Ctrl+S to save, Escape to cancel[/dim]")

    def action_save(self) -> None:
        matter_id = self.query_one("#matter-input", Input).value
        duration_str = self.query_one("#duration-input", Input).value
        narrative = self.query_one("#narrative-input", Input).value

        try:
            duration = int(duration_str)
        except ValueError:
            return

        edited = self._suggestion.model_copy(
            update={
                "matter_id": matter_id,
                "duration_minutes": duration,
                "narrative": narrative,
            }
        )
        self.dismiss((self._index, edited))

    def action_cancel(self) -> None:
        self.dismiss(None)
