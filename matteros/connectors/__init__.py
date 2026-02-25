from __future__ import annotations

from pathlib import Path

from matteros.connectors.base import ConnectorRegistry
from matteros.connectors.csv_export import CsvExportConnector
from matteros.connectors.filesystem import FilesystemConnector
from matteros.connectors.ms_graph_auth import MicrosoftGraphTokenManager
from matteros.connectors.ms_graph_calendar import MicrosoftGraphCalendarConnector
from matteros.connectors.ms_graph_mail import MicrosoftGraphMailConnector


def create_default_registry(*, auth_cache_path: Path | None = None) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    token_manager = MicrosoftGraphTokenManager(
        cache_path=(auth_cache_path or Path(".matteros/auth/ms_graph_token.json")).expanduser()
    )
    registry.register(MicrosoftGraphMailConnector(token_manager=token_manager))
    registry.register(MicrosoftGraphCalendarConnector(token_manager=token_manager))
    registry.register(FilesystemConnector())
    registry.register(CsvExportConnector())
    return registry
