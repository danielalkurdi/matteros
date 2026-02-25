from __future__ import annotations

from typing import Any

from matteros.connectors.base import Connector
from matteros.core.types import ConnectorManifest, PermissionMode


class PracticePantherConnector(Connector):
    """Sketch connector for PracticePanther legal practice management.

    Not yet implemented — defines the manifest and operation surface
    for future integration.
    """

    manifest = ConnectorManifest(
        connector_id="practice_panther",
        description="Read matters and log time via PracticePanther API (sketch)",
        default_mode=PermissionMode.READ,
        operations={
            "matters": PermissionMode.READ,
            "time_entries": PermissionMode.READ,
            "create_time_entry": PermissionMode.WRITE,
        },
    )

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        raise NotImplementedError(f"PracticePanther connector is not yet implemented (operation: {operation})")

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise NotImplementedError(f"PracticePanther connector is not yet implemented (operation: {operation})")
