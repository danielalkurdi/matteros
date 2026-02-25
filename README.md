# MatterOS

MatterOS is an open-source, self-hosted legal ops command center.

It is less "chat with a black box" and more "run explicit workflows with approvals, logs, and receipts."

## Why it exists

Legal work is fragmented across inboxes, calendars, documents, and matter systems. MatterOS focuses on the unglamorous but expensive part of the day:

- turning scattered activity into structured suggestions
- reviewing and approving side effects before they happen
- keeping an auditable record of what changed, when, and why

## What MatterOS can do today

- Playbook-driven workflow execution (`collect`, `transform`, `llm`, `approve`, `apply`)
- Dry-run planning with zero external writes
- Approval-gated apply steps for side effects
- Hash-chained audit logs in SQLite + JSONL with verification CLI
- Microsoft Graph calendar/mail, filesystem, CSV export connectors
- Optional Slack, Jira, GitHub, iCal connectors
- Local plugin connector discovery from `~/.matteros/plugins` or `<home>/plugins`
- Proactive drafts queue + review, learning, and digest commands
- Background daemon scheduler + activity watcher
- TUI dashboard + Web dashboard
- Team user/reporting primitives

## Install

### Homebrew

```bash
brew tap danielalkurdi/matteros
brew install danielalkurdi/matteros/matteros
```

### Source install (recommended for full feature set)

```bash
git clone https://github.com/danielalkurdi/matteros.git
cd matteros
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all,dev]'
```

### Python fallback (CLI-focused)

```bash
pipx install git+https://github.com/danielalkurdi/matteros.git
```

More install options: [docs/INSTALL.md](./docs/INSTALL.md)

## Quick start (5 minutes)

```bash
matteros init
matteros onboard --non-interactive --yes --skip-auth
matteros connectors list
matteros playbooks list

matteros run playbooks/daily_time_capture.yml \
  --dry-run \
  --input tests/fixtures/run_input.json

matteros audit show --last 20
matteros audit verify --run-id <RUN_ID> --source both
```

## Typical daily flow

Generate suggestions:

```bash
matteros run playbooks/daily_time_capture.yml \
  --dry-run \
  --input tests/fixtures/run_input.json
```

Review drafts interactively:

```bash
matteros review --limit 20
```

Learn from feedback history:

```bash
matteros learn --all
```

Get a weekly digest:

```bash
matteros digest --period week
```

## Interfaces

### CLI

```bash
matteros --help
```

### TUI

```bash
matteros tui
```

If `textual` is missing:

```bash
pip install -e '.[tui]'
```

### Web dashboard

```bash
matteros web --open
```

On startup, MatterOS prints a bootstrap URL with a one-time access token query parameter. Open that URL first. Keep it private.

If web dependencies are missing:

```bash
pip install -e '.[web]'
```

### Daemon

```bash
matteros daemon start
matteros daemon status
matteros daemon logs --lines 100
```

## Team mode

```bash
matteros team init --admin admin
matteros team add-user alice --role attorney
matteros team list-users
matteros team report matters
```

## Safety model

- Connectors declare explicit read/write operations.
- Policy blocks undeclared or invalid operations.
- Write side effects occur only in `apply` steps.
- Approval flow is explicit (`--approve`) and reviewable.
- Audit events are append-only and hash-linked.
- `matteros audit verify` validates chain integrity.
- Remote LLMs are opt-in; local provider is default.

Deep dive docs:

- [docs/policy-model.md](./docs/policy-model.md)
- [docs/audit-schema.md](./docs/audit-schema.md)
- [docs/threat-model.md](./docs/threat-model.md)
- [docs/connector-specs.md](./docs/connector-specs.md)

## LLM configuration

Core env vars:

- `MATTEROS_MODEL_PROVIDER`: `local` (default), `openai`, `anthropic`
- `MATTEROS_ALLOW_REMOTE_MODELS`: must be `true` for remote providers
- `MATTEROS_LLM_MODEL_ALLOWLIST`: optional comma-separated allowlist
- `MATTEROS_LLM_MAX_RETRIES`, `MATTEROS_LLM_RETRY_BACKOFF_SECONDS`
- `MATTEROS_LLM_TIMEOUT_SECONDS`

Provider keys:

- OpenAI: `OPENAI_API_KEY` (optional `OPENAI_MODEL`, `OPENAI_BASE_URL`)
- Anthropic: `ANTHROPIC_API_KEY` (optional `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_VERSION`)

Doctor command:

```bash
matteros llm doctor
```

## External provider contract tests (VCR)

Skipped by default.

Replay cassettes:

```bash
MATTEROS_RUN_EXTERNAL_TESTS=1 MATTEROS_VCR_RECORD_MODE=none pytest -q -m external
```

Record/update cassettes:

```bash
MATTEROS_RUN_EXTERNAL_TESTS=1 MATTEROS_VCR_RECORD_MODE=once pytest -q -m external
```

## License

AGPLv3 (`AGPL-3.0-only`).
