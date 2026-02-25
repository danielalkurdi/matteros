"""Factory functions for building MatterOS runtime components.

Extracted from cli.py so both CLI and TUI can share the same construction logic.
"""

from __future__ import annotations

from pathlib import Path

from matteros.connectors import create_default_registry
from matteros.connectors.base import ConnectorRegistry
from matteros.connectors.ms_graph_auth import DEFAULT_SCOPES, MicrosoftGraphTokenManager
from matteros.core.audit import AuditLogger
from matteros.core.config import load_config
from matteros.core.policy import PolicyEngine
from matteros.core.runner import WorkflowRunner
from matteros.core.store import SQLiteStore
from matteros.llm import LLMAdapter


def resolve_home(home: Path | None) -> Path:
    """Normalize .matteros home directory path."""
    if home is not None:
        return home.expanduser().resolve()
    return Path(".matteros").resolve()


def build_runner(home: Path) -> WorkflowRunner:
    """Construct a fully-wired WorkflowRunner from a home directory."""
    loaded = load_config(path=home / "config.yml", home=home)
    cfg = loaded.config

    store = SQLiteStore(home / "matteros.db")
    audit = AuditLogger(store, home / "audit" / "events.jsonl")
    return WorkflowRunner(
        store=store,
        connectors=create_default_registry(
            auth_cache_path=home / "auth" / "ms_graph_token.json",
            plugin_dir=home / "plugins",
        ),
        llm=LLMAdapter(
            default_provider=cfg.llm.provider,
            allow_remote_models=cfg.llm.remote_enabled,
            model_allowlist=cfg.llm.model_allowlist,
        ),
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
    """Construct a MicrosoftGraphTokenManager."""
    return MicrosoftGraphTokenManager(
        cache_path=home / "auth" / "ms_graph_token.json",
        tenant_id=tenant_id,
        client_id=client_id,
        scopes=scopes,
    )
