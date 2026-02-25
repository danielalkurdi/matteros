from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from matteros.connectors.base import Connector, ConnectorError, ensure_parent
from matteros.core.types import ConnectorManifest, PermissionMode


class CsvExportConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="csv_export",
        description="Export approved time entries to local CSV",
        default_mode=PermissionMode.WRITE,
        operations={"export_time_entries": PermissionMode.WRITE},
    )

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        raise ConnectorError("csv_export connector does not support read operations")

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        if operation != "export_time_entries":
            raise ConnectorError(f"unsupported csv_export operation: {operation}")

        output_path = Path(str(params.get("output_path", "time_entries.csv"))).expanduser()
        ensure_parent(output_path)

        rows = payload if isinstance(payload, list) else []
        fieldnames = [
            "matter_id",
            "client_id",
            "duration_minutes",
            "narrative",
            "confidence",
            "evidence_refs",
        ]

        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "matter_id": row.get("matter_id", ""),
                        "client_id": row.get("client_id", ""),
                        "duration_minutes": row.get("duration_minutes", 0),
                        "narrative": row.get("narrative", ""),
                        "confidence": row.get("confidence", 0),
                        "evidence_refs": ";".join(row.get("evidence_refs", [])),
                    }
                )

        return {
            "output_path": str(output_path),
            "rows_written": len(rows),
        }
