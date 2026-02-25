"""Tests for factory module (extracted from cli.py)."""

from __future__ import annotations

from pathlib import Path

from matteros.core.factory import build_runner, resolve_home


def test_resolve_home_with_explicit_path(tmp_path: Path) -> None:
    result = resolve_home(tmp_path / "custom")
    assert result == (tmp_path / "custom").resolve()


def test_resolve_home_default() -> None:
    result = resolve_home(None)
    assert result == Path(".matteros").resolve()


def test_build_runner_returns_runner(tmp_path: Path, runner_factory) -> None:
    runner, home = runner_factory("factory-home")
    assert runner is not None
    assert runner.store is not None
    assert runner.connectors is not None
    assert runner.audit is not None
    assert runner.policy is not None


def test_build_runner_registers_local_plugins(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plugin_dir = home / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "my_plugin.py").write_text(
        """
from matteros.connectors.base import Connector
from matteros.core.types import ConnectorManifest, PermissionMode

class MyPluginConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="my_plugin_connector",
        description="test plugin",
        default_mode=PermissionMode.READ,
        operations={"events": PermissionMode.READ},
    )

    def read(self, operation, params, context):
        return []

    def write(self, operation, params, payload, context):
        return {}
""".strip(),
        encoding="utf-8",
    )

    runner = build_runner(home)
    assert runner.connectors.get("my_plugin_connector").manifest.connector_id == "my_plugin_connector"
