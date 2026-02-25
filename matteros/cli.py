from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from matteros.connectors import create_default_registry
from matteros.connectors.ms_graph_auth import DEFAULT_SCOPES, MicrosoftGraphTokenManager
from matteros.core.audit import AuditLogger
from matteros.core.playbook import PlaybookError, load_playbook
from matteros.core.policy import PolicyEngine
from matteros.core.runner import RunnerOptions, WorkflowRunner
from matteros.core.store import SQLiteStore
from matteros.core.types import ApprovalDecision, TimeEntrySuggestion
from matteros.llm import LLMAdapter

app = typer.Typer(help="MatterOS legal ops workflow CLI")
connectors_app = typer.Typer(help="Manage connectors")
playbooks_app = typer.Typer(help="Inspect playbooks")
audit_app = typer.Typer(help="Inspect audit logs")
auth_app = typer.Typer(help="Manage authentication")
llm_app = typer.Typer(help="Inspect LLM runtime configuration")

app.add_typer(connectors_app, name="connectors")
app.add_typer(playbooks_app, name="playbooks")
app.add_typer(audit_app, name="audit")
app.add_typer(auth_app, name="auth")
app.add_typer(llm_app, name="llm")


def resolve_home(home: Path | None) -> Path:
    if home is not None:
        return home.expanduser().resolve()
    return Path(".matteros").resolve()


def build_runner(home: Path) -> WorkflowRunner:
    store = SQLiteStore(home / "matteros.db")
    audit = AuditLogger(store, home / "audit" / "events.jsonl")
    return WorkflowRunner(
        store=store,
        connectors=create_default_registry(auth_cache_path=home / "auth" / "ms_graph_token.json"),
        llm=LLMAdapter(),
        audit=audit,
        policy=PolicyEngine(),
    )


def build_ms_graph_token_manager(
    *,
    home: Path,
    tenant_id: str | None = None,
    client_id: str | None = None,
    scopes: str | None = None,
) -> MicrosoftGraphTokenManager:
    return MicrosoftGraphTokenManager(
        cache_path=home / "auth" / "ms_graph_token.json",
        tenant_id=tenant_id,
        client_id=client_id,
        scopes=scopes,
    )


@app.command("init")
def init_command(home: Path | None = typer.Option(None, help="MatterOS home directory")) -> None:
    """Create runtime directories, sqlite db, and an example playbook."""
    home_dir = resolve_home(home)
    home_dir.mkdir(parents=True, exist_ok=True)

    SQLiteStore(home_dir / "matteros.db")
    (home_dir / "audit").mkdir(parents=True, exist_ok=True)
    (home_dir / "auth").mkdir(parents=True, exist_ok=True)

    config_path = home_dir / "config.yml"
    if not config_path.exists():
        config_path.write_text(
            """model_provider: local
log_level: info
ms_graph_tenant_id: common
ms_graph_scopes: offline_access User.Read Mail.Read Calendars.Read
""",
            encoding="utf-8",
        )

    playbooks_dir = Path("playbooks")
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    sample_path = playbooks_dir / "daily_time_capture.yml"
    if not sample_path.exists():
        sample_payload = (Path(__file__).resolve().parent / "playbooks" / "daily_time_capture.yml").read_text(
            encoding="utf-8"
        )
        sample_path.write_text(sample_payload, encoding="utf-8")

    typer.echo(f"initialized MatterOS home: {home_dir}")
    typer.echo(f"sqlite db: {home_dir / 'matteros.db'}")
    typer.echo(f"example playbook: {sample_path}")


@connectors_app.command("list")
def connectors_list(
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """List installed connectors and permission manifests."""
    home_dir = resolve_home(home)
    registry = create_default_registry(auth_cache_path=home_dir / "auth" / "ms_graph_token.json")
    for manifest in registry.list():
        operations = ", ".join(
            f"{operation}:{mode.value}" for operation, mode in manifest.operations.items()
        )
        typer.echo(
            f"{manifest.connector_id} | default={manifest.default_mode.value} | {operations}"
        )


@auth_app.command("login")
def auth_login(
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
    tenant_id: str = typer.Option("common", "--tenant-id", help="Microsoft Entra tenant id"),
    client_id: str | None = typer.Option(
        None, "--client-id", help="App registration client id (or MATTEROS_MS_GRAPH_CLIENT_ID)"
    ),
    scopes: str = typer.Option(
        DEFAULT_SCOPES,
        "--scopes",
        help="Space-delimited OAuth scopes",
    ),
) -> None:
    """Perform Microsoft Graph device-code login and cache token."""
    home_dir = resolve_home(home)
    home_dir.mkdir(parents=True, exist_ok=True)
    (home_dir / "auth").mkdir(parents=True, exist_ok=True)

    manager = build_ms_graph_token_manager(
        home=home_dir,
        tenant_id=tenant_id,
        client_id=client_id,
        scopes=scopes,
    )

    try:
        manager.login_device_code(print_fn=typer.echo)
    except Exception as exc:
        typer.echo(f"auth login failed: {exc}")
        raise typer.Exit(code=1)

    status = manager.cache_status()
    expires_at = datetime.fromtimestamp(int(status.get("expires_at", 0)), tz=UTC).isoformat()
    typer.echo("microsoft graph login completed")
    typer.echo(f"token_cache: {manager.cache_path}")
    typer.echo(f"expires_at: {expires_at}")


@auth_app.command("status")
def auth_status(
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Show current Microsoft Graph token cache status."""
    home_dir = resolve_home(home)
    manager = build_ms_graph_token_manager(home=home_dir)
    status = manager.cache_status()
    state = str(status.get("status"))

    if state == "missing":
        typer.echo("microsoft_graph_token: missing")
        return

    expires_at = datetime.fromtimestamp(int(status.get("expires_at", 0)), tz=UTC).isoformat()
    typer.echo(f"microsoft_graph_token: {state}")
    typer.echo(f"tenant_id: {status.get('tenant_id')}")
    typer.echo(f"client_id: {status.get('client_id')}")
    typer.echo(f"scopes: {status.get('scopes')}")
    typer.echo(f"expires_at: {expires_at}")
    typer.echo(f"seconds_remaining: {status.get('seconds_remaining')}")


@auth_app.command("logout")
def auth_logout(
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Remove cached Microsoft Graph token."""
    home_dir = resolve_home(home)
    manager = build_ms_graph_token_manager(home=home_dir)
    if not manager.cache_path.exists():
        typer.echo("no cached token to remove")
        return

    manager.cache_path.unlink()
    typer.echo(f"removed cached token: {manager.cache_path}")


@llm_app.command("doctor")
def llm_doctor(
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Provider override for check: local|openai|anthropic",
    ),
) -> None:
    """Validate LLM provider configuration and policy controls."""
    adapter = LLMAdapter(default_provider=provider) if provider else LLMAdapter()
    selected_provider = provider or adapter.default_provider
    provider_instance = adapter.providers.get(selected_provider)
    if provider_instance is None:
        typer.echo(f"llm doctor: FAILED - unknown provider '{selected_provider}'")
        raise typer.Exit(code=1)

    model_name = _llm_model_name(provider_instance)
    findings: list[str] = []

    if selected_provider != "local" and not adapter.allow_remote_models:
        findings.append(
            "remote providers are disabled; set MATTEROS_ALLOW_REMOTE_MODELS=true"
        )

    if selected_provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        findings.append("OPENAI_API_KEY is not configured")

    if selected_provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        findings.append("ANTHROPIC_API_KEY is not configured")

    if (
        selected_provider != "local"
        and adapter.model_allowlist
        and model_name not in adapter.model_allowlist
    ):
        findings.append(
            f"model '{model_name}' is not allowed by MATTEROS_LLM_MODEL_ALLOWLIST"
        )

    typer.echo(f"provider: {selected_provider}")
    typer.echo(f"model: {model_name}")
    typer.echo(f"remote_enabled: {adapter.allow_remote_models}")
    typer.echo(f"max_retries: {adapter.max_retries}")
    typer.echo(f"retry_backoff_seconds: {adapter.retry_backoff_seconds}")
    typer.echo(
        "model_allowlist: "
        + (", ".join(adapter.model_allowlist) if adapter.model_allowlist else "<none>")
    )

    if findings:
        typer.echo("llm doctor: FAILED")
        for finding in findings:
            typer.echo(f"- {finding}")
        raise typer.Exit(code=1)

    typer.echo("llm doctor: OK")


@playbooks_app.command("list")
def playbooks_list(
    path: Path = typer.Option(Path("playbooks"), help="Directory to scan for playbooks"),
) -> None:
    """List available playbooks and required connectors."""
    target = path.expanduser().resolve()
    if not target.exists():
        typer.echo(f"playbook directory not found: {target}")
        raise typer.Exit(code=1)

    files = sorted(target.glob("*.yml")) + sorted(target.glob("*.yaml"))
    if not files:
        typer.echo(f"no playbooks found in {target}")
        return

    for file_path in files:
        try:
            playbook = load_playbook(file_path)
        except PlaybookError as exc:
            typer.echo(f"{file_path.name} | invalid | {exc}")
            continue

        connector_list = ", ".join(playbook.connectors)
        typer.echo(
            f"{file_path.name} | steps={len(playbook.steps)} | connectors={connector_list}"
        )


@app.command("run")
def run_command(
    playbook: Path = typer.Argument(..., help="Path to playbook YAML"),
    input_file: Path | None = typer.Option(None, "--input", help="JSON input file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Execute without side effects"),
    approve: bool = typer.Option(False, "--approve", help="Enable approval flow for side effects"),
    reviewer: str = typer.Option("cli-user", "--reviewer", help="Approval actor name"),
    approval_file: Path | None = typer.Option(
        None,
        "--approval-file",
        help="Optional JSON decisions for non-interactive approval",
    ),
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Run a playbook with optional dry-run and approval gating."""
    home_dir = resolve_home(home)
    runner = build_runner(home_dir)

    try:
        playbook_def = load_playbook(playbook.resolve())
    except PlaybookError as exc:
        typer.echo(f"playbook error: {exc}")
        raise typer.Exit(code=1)

    inputs: dict[str, Any] = {}
    if input_file is not None:
        payload = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            typer.echo("input JSON must be an object")
            raise typer.Exit(code=1)
        inputs = payload

    approval_handler = None
    if approve:
        if approval_file:
            approval_handler = _approval_handler_from_file(approval_file)
        else:
            approval_handler = _interactive_approval_handler

    options = RunnerOptions(
        dry_run=dry_run,
        approve_mode=approve,
        reviewer=reviewer,
        approval_handler=approval_handler,
    )

    try:
        summary = runner.run(playbook=playbook_def, inputs=inputs, options=options)
    except Exception as exc:
        typer.echo(f"run failed: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"run_id: {summary.run_id}")
    typer.echo(f"status: {summary.status.value}")

    source_counts: list[str] = []
    for source_key in ("calendar_events", "sent_emails", "file_activity"):
        value = summary.outputs.get(source_key)
        if isinstance(value, list):
            source_counts.append(f"{source_key}={len(value)}")
    if source_counts:
        typer.echo(f"data_sources: {', '.join(source_counts)}")

    suggestions = summary.outputs.get("time_entry_suggestions", [])
    if isinstance(suggestions, list) and suggestions:
        typer.echo("proposed_time_entries:")
        for item in suggestions:
            entry = TimeEntrySuggestion.model_validate(item)
            typer.echo(
                f"- matter={entry.matter_id} duration={entry.duration_minutes}m confidence={entry.confidence} narrative={entry.narrative}"
            )

    apply_result = summary.outputs.get("apply_time_entries")
    if apply_result:
        typer.echo(f"apply_result: {json.dumps(apply_result, sort_keys=True)}")


@audit_app.command("show")
def audit_show(
    last: int = typer.Option(20, "--last", min=1, help="Number of events to show"),
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Show recent audit events."""
    home_dir = resolve_home(home)
    store = SQLiteStore(home_dir / "matteros.db")
    events = store.list_audit_events(limit=last)
    for event in events:
        typer.echo(
            f"#{event['seq']} run={event['run_id']} {event['timestamp']} {event['event_type']} actor={event['actor']} step={event['step_id']}"
        )


@audit_app.command("export")
def audit_export(
    run_id: str = typer.Option(..., "--run-id", help="Run identifier"),
    format: str = typer.Option("json", "--format", help="json|jsonl"),
    output: Path | None = typer.Option(None, "--output", help="Output file path"),
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Export audit events for a run."""
    home_dir = resolve_home(home)
    store = SQLiteStore(home_dir / "matteros.db")
    events = store.export_audit_for_run(run_id)

    if format not in {"json", "jsonl"}:
        typer.echo("format must be json or jsonl")
        raise typer.Exit(code=1)

    if format == "json":
        payload = json.dumps(events, indent=2, sort_keys=True)
    else:
        payload = "\n".join(json.dumps(event, sort_keys=True) for event in events)

    if output:
        output.write_text(payload + ("\n" if not payload.endswith("\n") else ""), encoding="utf-8")
        typer.echo(f"exported {len(events)} events to {output}")
        return

    typer.echo(payload)


@audit_app.command("verify")
def audit_verify(
    run_id: str = typer.Option(..., "--run-id", help="Run identifier"),
    source: str = typer.Option("both", "--source", help="db|jsonl|both"),
    home: Path | None = typer.Option(None, help="MatterOS home directory"),
) -> None:
    """Verify audit hash-chain integrity for a run."""
    source_name = source.strip().lower()
    if source_name not in {"db", "jsonl", "both"}:
        typer.echo("source must be db, jsonl, or both")
        raise typer.Exit(code=2)

    home_dir = resolve_home(home)
    store = SQLiteStore(home_dir / "matteros.db")
    audit = AuditLogger(store, home_dir / "audit" / "events.jsonl")

    try:
        result = audit.verify_run(run_id=run_id, source=source_name)
    except FileNotFoundError as exc:
        typer.echo(f"audit verify error: {exc}")
        raise typer.Exit(code=2)

    if result.ok:
        typer.echo(
            f"audit verified: run={result.run_id} source={result.source} "
            f"events={result.checked_events} last_seq={result.last_seq} "
            f"last_hash={result.last_event_hash}"
        )
        return

    failure = f"audit verification failed: reason={result.reason}"
    if result.failure_seq is not None:
        failure += f" seq={result.failure_seq}"
    if result.details:
        failure += f" details={result.details}"
    typer.echo(failure)

    if result.reason == "missing_event" and result.checked_events == 0:
        raise typer.Exit(code=2)
    raise typer.Exit(code=1)


def _interactive_approval_handler(
    suggestion: TimeEntrySuggestion,
    index: int,
) -> ApprovalDecision:
    typer.echo(
        f"[{index}] matter={suggestion.matter_id} duration={suggestion.duration_minutes}m confidence={suggestion.confidence}"
    )
    typer.echo(f"narrative: {suggestion.narrative}")

    approved = typer.confirm("approve this entry?", default=True)
    if not approved:
        reason = typer.prompt("rejection reason", default="reviewer rejected")
        return ApprovalDecision(decision="reject", reason=reason)

    narrative = typer.prompt("narrative", default=suggestion.narrative)
    duration_input = typer.prompt(
        "duration_minutes",
        default=str(suggestion.duration_minutes),
    )

    try:
        duration = int(duration_input)
    except ValueError as exc:
        raise typer.BadParameter("duration_minutes must be integer") from exc

    edited = suggestion.model_copy(update={"narrative": narrative, "duration_minutes": duration})
    return ApprovalDecision(decision="approve", edited_entry=edited)


def _approval_handler_from_file(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter("approval-file must be a list of decisions")

    decisions: dict[int, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if "index" not in item:
            continue
        decisions[int(item["index"])] = item

    def handler(suggestion: TimeEntrySuggestion, index: int) -> ApprovalDecision:
        selected = decisions.get(index)
        if not selected:
            return ApprovalDecision(decision="reject", reason="missing decision")

        decision = str(selected.get("decision", "reject"))
        reason = selected.get("reason")
        if decision != "approve":
            return ApprovalDecision(decision="reject", reason=str(reason) if reason else None)

        updated = suggestion.model_copy(
            update={
                "narrative": selected.get("narrative", suggestion.narrative),
                "duration_minutes": int(
                    selected.get("duration_minutes", suggestion.duration_minutes)
                ),
            }
        )
        try:
            return ApprovalDecision(decision="approve", edited_entry=updated)
        except ValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    return handler


def _llm_model_name(provider_instance: Any) -> str:
    value = getattr(provider_instance, "model_name", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
