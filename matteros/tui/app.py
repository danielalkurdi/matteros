"""MatterOS TUI application — the solo lawyer's command center.

Launch with: matteros tui [--home PATH]
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from matteros.core.config import load_config
from matteros.core.events import EventBus, EventType, RunEvent
from matteros.core.factory import resolve_home
from matteros.core.store import SQLiteStore
from matteros.tui.screens.approval_screen import ApprovalScreen
from matteros.tui.screens.audit_screen import AuditScreen
from matteros.tui.screens.run_screen import RunScreen
from matteros.tui.widgets.event_log import EventLog


class MatterOSApp(App):
    """MatterOS interactive TUI dashboard."""

    TITLE = "MatterOS"
    SUB_TITLE = "Legal Ops Command Center"

    CSS = """
    #sidebar {
        width: 28;
        border-right: tall $accent;
        padding: 1;
    }
    #sidebar ListView {
        height: auto;
    }
    #main-content {
        width: 1fr;
        padding: 1;
    }
    #dashboard-stats {
        height: auto;
        padding: 1;
        border-bottom: tall $accent;
    }
    #recent-runs {
        height: 1fr;
    }
    #status-footer {
        height: 1;
        dock: bottom;
        background: $accent;
        padding: 0 1;
    }
    .stat-box {
        width: 1fr;
        height: 3;
        border: tall $accent;
        padding: 0 1;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("d", "show_dashboard", "Dashboard"),
        ("r", "show_run", "Run Playbook"),
        ("a", "show_audit", "Audit Log"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, home: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.home = resolve_home(home)
        self.event_bus = EventBus()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("[bold]Navigation[/bold]\n")
                yield ListView(
                    ListItem(Label("Dashboard"), id="nav-dashboard"),
                    ListItem(Label("Run Playbook"), id="nav-run"),
                    ListItem(Label("Approval Queue"), id="nav-approval"),
                    ListItem(Label("Audit Log"), id="nav-audit"),
                    id="nav-list",
                )
                yield Label("\n[bold]Quick Info[/bold]")
                yield Static("Loading...", id="sidebar-info")
            with Vertical(id="main-content"):
                with Horizontal(id="dashboard-stats"):
                    yield Static("", id="stat-runs", classes="stat-box")
                    yield Static("", id="stat-pending", classes="stat-box")
                    yield Static("", id="stat-approved", classes="stat-box")
                yield Label("[bold]Recent Runs[/bold]")
                yield DataTable(id="recent-runs")
        yield Static("Ready", id="status-footer")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_dashboard()
        self.event_bus.subscribe(None, self._on_event)

    def _refresh_dashboard(self) -> None:
        try:
            store = SQLiteStore(self.home / "matteros.db")
        except Exception:
            self.query_one("#sidebar-info", Static).update("No database found")
            return

        loaded = load_config(path=self.home / "config.yml", home=self.home)
        cfg = loaded.config

        info_text = (
            f"Home: {self.home.name}\n"
            f"Profile: {cfg.profile.name}\n"
            f"LLM: {cfg.llm.provider}"
        )
        self.query_one("#sidebar-info", Static).update(info_text)

        # Load stats from DB
        try:
            conn = store._connect()
            run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE decision = 'pending'"
            ).fetchone()[0]
            approved = conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE decision = 'approve'"
            ).fetchone()[0]
            conn.close()
        except Exception:
            run_count = pending = approved = 0

        self.query_one("#stat-runs", Static).update(f"[bold]Runs[/bold]\n{run_count}")
        self.query_one("#stat-pending", Static).update(f"[bold]Pending[/bold]\n{pending}")
        self.query_one("#stat-approved", Static).update(f"[bold]Approved[/bold]\n{approved}")

        # Recent runs table
        table = self.query_one("#recent-runs", DataTable)
        table.clear(columns=True)
        table.add_columns("Run ID", "Playbook", "Status", "Started", "Dry Run")
        table.cursor_type = "row"

        try:
            conn = store._connect()
            rows = conn.execute(
                "SELECT id, playbook_name, status, started_at, dry_run FROM runs ORDER BY started_at DESC LIMIT 20"
            ).fetchall()
            conn.close()
            for row in rows:
                table.add_row(
                    str(row[0])[:8],
                    str(row[1]),
                    str(row[2]),
                    str(row[3])[:19],
                    "yes" if row[4] else "no",
                )
        except Exception:
            pass

    def _on_event(self, event: RunEvent) -> None:
        status = self.query_one("#status-footer", Static)
        status.update(f"Event: {event.event_type.value} run={event.run_id[:8]}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id == "nav-dashboard":
            self._refresh_dashboard()
        elif item_id == "nav-run":
            self.action_show_run()
        elif item_id == "nav-approval":
            self._show_approval()
        elif item_id == "nav-audit":
            self.action_show_audit()

    def action_show_dashboard(self) -> None:
        self._refresh_dashboard()

    def action_show_run(self) -> None:
        loaded = load_config(path=self.home / "config.yml", home=self.home)
        playbook_path = Path(loaded.config.paths.default_playbook)
        workspace_path = Path(loaded.config.paths.workspace_path)
        fixtures_root = loaded.config.paths.fixtures_root

        inputs = {
            "date": datetime.now(UTC).date().isoformat(),
            "workspace_path": str(workspace_path),
            "fixtures_root": str(fixtures_root or ""),
            "output_csv_path": str(self.home / "exports" / "tui_entries.csv"),
            "matter_hint": "",
        }

        self.push_screen(RunScreen(
            home=self.home,
            playbook_path=playbook_path,
            inputs=inputs,
            dry_run=True,
        ))

    def _show_approval(self) -> None:
        # Load latest suggestions from most recent run
        try:
            store = SQLiteStore(self.home / "matteros.db")
            conn = store._connect()
            row = conn.execute(
                "SELECT output_json FROM runs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            conn.close()

            if row and row[0]:
                import json
                outputs = json.loads(row[0])
                suggestions = outputs.get("time_entry_suggestions", [])
                if suggestions:
                    self.push_screen(ApprovalScreen(suggestions))
                    return
        except Exception:
            pass

        self.query_one("#status-footer", Static).update("No pending suggestions found")

    def action_show_audit(self) -> None:
        self.push_screen(AuditScreen(self.home))


def run_tui(home: Path | None = None) -> None:
    """Entry point for the TUI."""
    app = MatterOSApp(home=home)
    app.run()
