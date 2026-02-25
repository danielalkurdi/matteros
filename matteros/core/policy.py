from __future__ import annotations

from typing import Any

from matteros.core.types import ConnectorManifest, PermissionMode, PlaybookDefinition, PlaybookStep


class PolicyError(Exception):
    """Raised when a policy rule is violated."""


class PolicyEngine:
    def ensure_declared_connectors(
        self,
        playbook: PlaybookDefinition,
        available_manifests: dict[str, ConnectorManifest],
    ) -> None:
        missing = sorted(set(playbook.connectors) - set(available_manifests))
        if missing:
            raise PolicyError(f"playbook requires missing connectors: {', '.join(missing)}")

    def validate_operation(
        self,
        *,
        step: PlaybookStep,
        manifest: ConnectorManifest,
        operation: str,
        dry_run: bool,
        approve_mode: bool,
    ) -> None:
        mode = manifest.operations.get(operation)
        if mode is None:
            raise PolicyError(
                f"connector {manifest.connector_id} does not expose operation {operation}"
            )

        if step.type != "apply" and mode == PermissionMode.WRITE:
            raise PolicyError(
                f"write operation {operation} is not allowed outside apply steps"
            )

        if mode == PermissionMode.WRITE:
            if dry_run:
                return
            if not approve_mode:
                raise PolicyError(
                    "write operation blocked: run was not started with --approve"
                )

    def sanitize_untrusted_data(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self.sanitize_untrusted_data(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.sanitize_untrusted_data(item) for item in value]
        if isinstance(value, str):
            # Preserve user data while removing control characters that can break logs/prompts.
            return "".join(ch for ch in value if ch.isprintable() or ch in "\n\t")
        return value
