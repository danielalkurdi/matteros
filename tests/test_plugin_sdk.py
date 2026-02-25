"""Tests for the Plugin SDK."""

from __future__ import annotations

from pathlib import Path

from matteros.connectors.base import ConnectorRegistry
from matteros.connectors.plugin import discover_plugins, register_plugins, scan_plugin_dir


def test_discover_plugins_returns_list() -> None:
    plugins = discover_plugins()
    assert isinstance(plugins, list)


def test_scan_plugin_dir_nonexistent(tmp_path: Path) -> None:
    result = scan_plugin_dir(tmp_path / "nonexistent")
    assert result == []


def test_scan_plugin_dir_with_packages(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()

    pkg = plugin_dir / "my_plugin"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    (plugin_dir / "standalone.py").write_text("", encoding="utf-8")

    result = scan_plugin_dir(plugin_dir)
    assert "my_plugin" in result
    assert "standalone" in result


def test_discover_plugins_loads_local_module_connector(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "local_plugin.py"
    plugin_file.write_text(
        """
from matteros.connectors.base import Connector
from matteros.core.types import ConnectorManifest, PermissionMode

class LocalPluginConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="local_plugin",
        description="local plugin",
        default_mode=PermissionMode.READ,
        operations={"ping": PermissionMode.READ},
    )

    def read(self, operation, params, context):
        return [{"ok": True}]

    def write(self, operation, params, payload, context):
        return {"ok": True}
""".strip(),
        encoding="utf-8",
    )

    plugins = discover_plugins(plugin_dir=plugin_dir)
    connector_ids = {plugin.manifest.connector_id for plugin in plugins}
    assert "local_plugin" in connector_ids


def test_register_plugins_registers_local_connector(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    pkg = plugin_dir / "test_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        """
from matteros.connectors.base import Connector
from matteros.core.types import ConnectorManifest, PermissionMode

class PkgConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="pkg_plugin",
        description="pkg plugin",
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

    registry = ConnectorRegistry()
    registered = register_plugins(registry, plugin_dir=plugin_dir)
    assert "pkg_plugin" in registered
    assert registry.get("pkg_plugin").manifest.connector_id == "pkg_plugin"
