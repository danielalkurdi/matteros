# Policy Model

## Enforced rules

- Playbook connector declarations must match installed connectors.
- Step operation must exist in connector permission manifest.
- Write operations are blocked outside `apply` steps.
- Write operations require `--approve` unless `--dry-run`.
- Connector data is sanitized before entering shared context.

## Safety defaults

- Read-only data collection connectors.
- Human approval gate before all external side effects.
- Structured schema validation for model-generated entries.
- Local model provider default; remote providers require explicit opt-in.
- Optional exact model allowlist enforcement via `MATTEROS_LLM_MODEL_ALLOWLIST`.
