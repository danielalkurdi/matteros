"""Run screen: execute a playbook and show live step progress."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

from matteros.core.events import EventBus, EventType, RunEvent
from matteros.core.factory import build_runner
from matteros.core.playbook import load_playbook
from matteros.core.runner import RunnerOptions
from matteros.core.types import RunSummary
from matteros.tui.widgets.event_log import EventLog
from matteros.tui.widgets.step_pipeline import StepPipeline


class RunScreen(Screen):
    """Screen for running a playbook with live output."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "rerun", "Re-run"),
    ]

    DEFAULT_CSS = """
    RunScreen {
        layout: horizontal;
    }
    RunScreen #sidebar {
        width: 30;
        border-right: tall $accent;
        padding: 1;
    }
    RunScreen #main {
        width: 1fr;
    }
    RunScreen #pipeline {
        height: auto;
        max-height: 50%;
        border-bottom: tall $accent;
    }
    RunScreen #log {
        height: 1fr;
    }
    RunScreen #status-bar {
        height: 1;
        dock: bottom;
        background: $accent;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        home: Path,
        playbook_path: Path,
        inputs: dict[str, Any] | None = None,
        dry_run: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.home = home
        self.playbook_path = playbook_path
        self.run_inputs = inputs or {}
        self.dry_run = dry_run
        self.event_bus = EventBus()
        self._summary: RunSummary | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(f"[bold]Playbook[/bold]\n{self.playbook_path.name}")
                yield Label(f"\n[bold]Mode[/bold]\n{'dry-run' if self.dry_run else 'live'}")
                yield StepPipeline(id="pipeline-widget")
            with Vertical(id="main"):
                yield Static("[bold]Step Pipeline[/bold]", id="pipeline-header")
                yield StepPipeline(id="pipeline")
                yield Static("[bold]Event Log[/bold]")
                yield EventLog(id="log", highlight=True, markup=True)
        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.event_bus.subscribe(None, self._on_event)
        self._start_run()

    def _on_event(self, event: RunEvent) -> None:
        log = self.query_one("#log", EventLog)
        pipeline = self.query_one("#pipeline", StepPipeline)
        status_bar = self.query_one("#status-bar", Static)

        log.append_event(event.event_type.value, event.step_id, event.data)

        if event.event_type == EventType.STEP_STARTED and event.step_id:
            pipeline.update_step_status(event.step_id, "running")
            status_bar.update(f"Running: {event.step_id}")
        elif event.event_type == EventType.STEP_COMPLETED and event.step_id:
            pipeline.update_step_status(event.step_id, "completed")
        elif event.event_type == EventType.STEP_FAILED and event.step_id:
            pipeline.update_step_status(event.step_id, "failed")
        elif event.event_type == EventType.RUN_COMPLETED:
            status_bar.update("[green]Run completed[/green]")
        elif event.event_type == EventType.RUN_FAILED:
            status_bar.update(f"[red]Run failed: {event.data.get('error', '')}[/red]")

    @work(thread=True)
    def _start_run(self) -> None:
        try:
            playbook = load_playbook(self.playbook_path)
            pipeline = self.query_one("#pipeline", StepPipeline)
            pipeline.set_steps([
                {"id": step.id, "type": step.type.value, "status": "pending"}
                for step in playbook.steps
            ])

            runner = build_runner(self.home)
            runner.event_bus = self.event_bus

            self._summary = runner.run(
                playbook=playbook,
                inputs=self.run_inputs,
                options=RunnerOptions(
                    dry_run=self.dry_run,
                    approve_mode=False,
                    reviewer="tui-user",
                ),
            )
        except Exception as exc:
            log = self.query_one("#log", EventLog)
            log.write(f"[red]Error: {exc}[/red]")

    def action_rerun(self) -> None:
        log = self.query_one("#log", EventLog)
        log.clear()
        self._start_run()
