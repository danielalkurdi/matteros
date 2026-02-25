# Policy Model

MatterOS policy checks are designed to keep automation explicit and reviewable.

## Enforced rules

- Playbook connector declarations must match installed connectors.
- Step operations must exist in connector permission manifests.
- Write operations are blocked outside `apply` steps.
- Write operations require `--approve` unless `--dry-run` is active.
- Connector payloads are treated as untrusted and sanitized before shared context use.

## Safety defaults

- Read-first collection model.
- Human-in-the-loop approval before external side effects.
- Structured schema validation for model-generated entries.
- Audit events are append-only and hash-linked.
- Local LLM provider default; remote providers are explicit opt-in.
- Optional exact model allowlist via `MATTEROS_LLM_MODEL_ALLOWLIST`.

## Web and access safeguards

- Web UI requires an access token bootstrap URL or bearer token.
- Session bootstrap tokens are generated per web process start.
- Draft approve/reject endpoints are protected by the same web auth middleware.

## Connector/plugin scope

- Built-in connectors publish explicit operation modes (`read` / `write`).
- Plugin connectors must publish valid manifests.
- Conflicting plugin IDs are skipped instead of overriding existing connectors.
