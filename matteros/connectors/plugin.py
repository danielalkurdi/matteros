"""Plugin SDK for third-party MatterOS connectors.

Connectors are discovered from:
1) Installed entry-points in the ``matteros.connectors`` group
2) Local modules/packages under ``~/.matteros/plugins`` (or a supplied directory)

Third-party connectors may register via pip entry-points:

    [project.entry-points."matteros.connectors"]
    my_connector = "my_package:MyConnector"
"""

from __future__ import annotations

import logging
from importlib import util
from importlib.metadata import entry_points
from inspect import getmembers, isclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from matteros.connectors.base import Connector, ConnectorRegistry

if TYPE_CHECKING:
    from importlib.metadata import EntryPoint

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "matteros.connectors"
DEFAULT_PLUGIN_DIR = Path("~/.matteros/plugins").expanduser()


def discover_plugins(*, plugin_dir: Path | None = None) -> list[Connector]:
    """Load valid connectors from entry-points and local plugin files."""

    connectors: list[Connector] = []
    seen_ids: set[str] = set()

    for connector in _discover_entrypoint_plugins():
        connector_id = connector.manifest.connector_id
        if connector_id in seen_ids:
            logger.warning("duplicate plugin connector id %r; skipping", connector_id)
            continue
        seen_ids.add(connector_id)
        connectors.append(connector)

    local_dir = (plugin_dir or DEFAULT_PLUGIN_DIR).expanduser()
    for connector in _discover_local_plugins(local_dir):
        connector_id = connector.manifest.connector_id
        if connector_id in seen_ids:
            logger.warning("duplicate plugin connector id %r; skipping", connector_id)
            continue
        seen_ids.add(connector_id)
        connectors.append(connector)

    return connectors


def _discover_entrypoint_plugins() -> list[Connector]:
    eps: list[EntryPoint] = list(entry_points(group=ENTRY_POINT_GROUP))
    connectors: list[Connector] = []

    for ep in eps:
        try:
            cls = ep.load()
        except Exception:
            logger.warning("failed to load plugin entry-point %r", ep.name, exc_info=True)
            continue

        if not (isinstance(cls, type) and issubclass(cls, Connector)):
            logger.warning(
                "plugin %r does not resolve to a Connector subclass (got %r)",
                ep.name,
                cls,
            )
            continue

        try:
            instance = cls()
        except Exception:
            logger.warning("failed to instantiate plugin %r", ep.name, exc_info=True)
            continue

        if not hasattr(instance, "manifest") or instance.manifest is None:
            logger.warning("plugin %r has no valid manifest", ep.name)
            continue

        connectors.append(instance)
        logger.info("discovered plugin connector %r", instance.manifest.connector_id)

    return connectors


def _discover_local_plugins(plugin_dir: Path) -> list[Connector]:
    if not plugin_dir.is_dir():
        return []

    discovered: list[Connector] = []
    for name, source_path in _iter_local_plugin_sources(plugin_dir):
        module = _load_module_from_file(name=name, source_path=source_path)
        if module is None:
            continue

        for connector in _extract_connectors_from_module(module):
            discovered.append(connector)
            logger.info(
                "discovered local plugin connector %r from %s",
                connector.manifest.connector_id,
                source_path,
            )

    return discovered


def _iter_local_plugin_sources(plugin_dir: Path) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for child in sorted(plugin_dir.iterdir()):
        if child.is_dir():
            init_path = child / "__init__.py"
            if init_path.exists():
                sources.append((child.name, init_path))
            continue
        if child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            sources.append((child.stem, child))
    return sources


def _load_module_from_file(*, name: str, source_path: Path) -> ModuleType | None:
    module_name = f"matteros_user_plugin_{name}_{abs(hash(str(source_path.resolve()))):x}"
    submodule_locations = [str(source_path.parent)] if source_path.name == "__init__.py" else None
    spec = util.spec_from_file_location(
        module_name,
        source_path,
        submodule_search_locations=submodule_locations,
    )
    if spec is None or spec.loader is None:
        logger.warning("failed to build import spec for plugin %r", source_path)
        return None

    module = util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("failed to import local plugin %r", source_path, exc_info=True)
        return None
    return module


def _extract_connectors_from_module(module: ModuleType) -> list[Connector]:
    connectors: list[Connector] = []
    seen_classes: set[type[Any]] = set()

    explicit_candidates: list[Any] = []
    if hasattr(module, "CONNECTOR"):
        explicit_candidates.append(getattr(module, "CONNECTOR"))
    if hasattr(module, "CONNECTOR_CLASS"):
        explicit_candidates.append(getattr(module, "CONNECTOR_CLASS"))
    if hasattr(module, "get_connector"):
        explicit_candidates.append(getattr(module, "get_connector"))

    for name, cls in getmembers(module, isclass):
        if name.startswith("_"):
            continue
        if not issubclass(cls, Connector) or cls is Connector:
            continue
        if cls.__module__ != module.__name__:
            continue
        if cls in seen_classes:
            continue
        seen_classes.add(cls)
        explicit_candidates.append(cls)

    for candidate in explicit_candidates:
        connector = _coerce_connector(candidate)
        if connector is None:
            continue
        if not hasattr(connector, "manifest") or connector.manifest is None:
            logger.warning("plugin candidate %r has no valid manifest", candidate)
            continue
        connectors.append(connector)

    return connectors


def _coerce_connector(candidate: Any) -> Connector | None:
    # Already-instantiated connector.
    if isinstance(candidate, Connector):
        return candidate

    # Connector class.
    if isinstance(candidate, type) and issubclass(candidate, Connector):
        try:
            return candidate()
        except Exception:
            logger.warning("failed to instantiate plugin class %r", candidate, exc_info=True)
            return None

    # Factory function.
    if callable(candidate):
        try:
            produced = candidate()
        except Exception:
            logger.warning("failed to call plugin factory %r", candidate, exc_info=True)
            return None
        return _coerce_connector(produced)

    return None


def register_plugins(registry: ConnectorRegistry, *, plugin_dir: Path | None = None) -> list[str]:
    """Discover plugins and register each into *registry*.

    Returns the list of registered connector IDs.
    """

    registered: list[str] = []
    existing = set(registry.manifests())
    for connector in discover_plugins(plugin_dir=plugin_dir):
        try:
            connector_id = connector.manifest.connector_id
            if connector_id in existing:
                logger.warning("skipping plugin %r; connector id already registered", connector_id)
                continue
            registry.register(connector)
            existing.add(connector_id)
            registered.append(connector_id)
        except Exception:
            logger.warning(
                "failed to register plugin %r",
                connector.manifest.connector_id,
                exc_info=True,
            )
    return registered


def scan_plugin_dir(plugin_dir: Path) -> list[str]:
    """Return package names found under *plugin_dir* (informational).

    Looks for directories containing ``__init__.py`` or ``.py`` files at the
    top level.  This does **not** load them; it is meant for the CLI to show
    what lives in ``~/.matteros/plugins/``.
    """

    if not plugin_dir.is_dir():
        return []

    names: list[str] = []
    for child in sorted(plugin_dir.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            names.append(child.name)
        elif child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            names.append(child.stem)
    return names
