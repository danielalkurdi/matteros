# Audit Schema

Each audit event records:

- `seq`: monotonically increasing row id
- `run_id`: workflow run id
- `timestamp`: UTC ISO timestamp
- `event_type`: lifecycle event identifier
- `actor`: `system` or reviewer id
- `step_id`: nullable step identifier
- `data`: event-specific payload
- `prev_hash`: previous event hash for run
- `event_hash`: SHA-256 over canonical event payload + `prev_hash`

Audit events are written to both SQLite (`audit_events`) and JSONL (`.matteros/audit/events.jsonl`).

## Verification Rules

- Verification is run-scoped: only events with matching `run_id` are considered.
- Event order is ascending `seq` for both SQLite and JSONL verification.
- Canonical payload uses sorted JSON keys and compact separators with the fields:
  `run_id`, `timestamp`, `event_type`, `actor`, `step_id`, `data`, `prev_hash`.
- Hash derivation is `SHA256((prev_hash or "") + canonical_payload)`.
- Chain linkage must hold:
  - first event has `prev_hash = null`
  - every next event has `prev_hash == previous.event_hash`
- `matteros audit verify --source both` verifies DB and JSONL independently, then cross-checks
  matching `seq` rows and `event_hash` values across both sources.

## Verification Failure Reasons

- `missing_event`: no events for run, or event exists in one source but not the other.
- `event_hash_mismatch`: stored `event_hash` does not match recomputed hash from payload.
- `prev_hash_mismatch`: chain link mismatch (broken linkage or out-of-order data).
- `parse_error`: malformed audit record shape or invalid JSONL line.

## CLI Contract

```bash
matteros audit verify --run-id <RUN_ID> [--source db|jsonl|both] [--home <PATH>]
```

- exit code `0`: verification passed
- exit code `1`: chain/content verification failed
- exit code `2`: invalid command input or missing run events
