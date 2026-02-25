from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from matteros.connectors.base import Connector, ConnectorError
from matteros.core.types import ConnectorManifest, PermissionMode

_VEVENT_RE = re.compile(r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT", re.DOTALL)
_FIELD_RE = re.compile(r"^([A-Z\-;]+?):(.*)$", re.MULTILINE)


class ICalConnector(Connector):
    manifest = ConnectorManifest(
        connector_id="ical",
        description="Read events from local iCal (.ics) files",
        default_mode=PermissionMode.READ,
        operations={"events": PermissionMode.READ},
    )

    def read(self, operation: str, params: dict[str, Any], context: dict[str, Any]) -> Any:
        if operation != "events":
            raise ConnectorError(f"unsupported ical read operation: {operation}")

        ics_path = params.get("path")
        if not ics_path:
            raise ConnectorError("ical events operation requires a path param")

        path = Path(str(ics_path)).expanduser()
        if not path.exists():
            raise ConnectorError(f"ics file not found: {path}")

        content = path.read_text(encoding="utf-8")
        return self._parse_events(content)

    def write(self, operation: str, params: dict[str, Any], payload: Any, context: dict[str, Any]) -> Any:
        raise ConnectorError("ical connector is read-only")

    def _parse_events(self, content: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for match in _VEVENT_RE.finditer(content):
            block = match.group(1)
            # Unfold continuation lines (RFC 5545 sec 3.1)
            block = re.sub(r"\r?\n[ \t]", "", block)
            fields: dict[str, str] = {}
            for field_match in _FIELD_RE.finditer(block):
                key = field_match.group(1).split(";")[0].strip()
                value = field_match.group(2).strip()
                fields[key] = value

            event: dict[str, Any] = {
                "summary": fields.get("SUMMARY", ""),
                "uid": fields.get("UID", ""),
                "dtstart": self._parse_ical_dt(fields.get("DTSTART")),
                "dtend": self._parse_ical_dt(fields.get("DTEND")),
            }
            events.append(event)
        return events

    def _parse_ical_dt(self, value: str | None) -> str | None:
        if not value:
            return None
        # Handle TZID parameter prefix already stripped by key split
        clean = value.strip()
        try:
            if "T" in clean:
                if clean.endswith("Z"):
                    dt = datetime.strptime(clean, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                else:
                    dt = datetime.strptime(clean, "%Y%m%dT%H%M%S")
                    dt = dt.replace(tzinfo=UTC)
            else:
                dt = datetime.strptime(clean, "%Y%m%d").replace(tzinfo=UTC)
            return dt.isoformat()
        except ValueError:
            return clean
