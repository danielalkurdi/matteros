from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode


class FilesystemConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="filesystem",
        description="Scan local file metadata for activity",
        default_mode=PermissionMode.READ,
        operations={"activity_metadata": PermissionMode.READ},
    )

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "activity_metadata":
            raise ConnectorError(f"unsupported filesystem operation: {operation}")

        root_path = Path(str(params.get("root_path", "."))).expanduser()
        if not root_path.exists():
            raise ConnectorError(f"filesystem root_path not found: {root_path}")

        max_files = int(params.get("max_files", 500))
        start = self._parse_optional_iso(params.get("start"))
        end = self._parse_optional_iso(params.get("end"))

        events: list[dict[str, Any]] = []
        for path in root_path.rglob("*"):
            if len(events) >= max_files:
                break
            if not path.is_file():
                continue

            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            if start and modified < start:
                continue
            if end and modified > end:
                continue

            events.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified_at": modified.isoformat(),
                }
            )

        return events

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("filesystem connector is read-only")

    def _parse_optional_iso(self, value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
