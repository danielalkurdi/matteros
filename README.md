# MatterOS

MatterOS is an open-source, self-hostable legal ops orchestration CLI.

MVP focus:
- Activity-to-Time workflow for non-billable admin reduction
- Microsoft-first connectors (Outlook sent mail + Calendar) plus filesystem metadata
- Human approval before side effects
- Immutable audit log for defensibility

## Install (Homebrew first)

```bash
brew tap danielalkurdi/matteros
brew install matteros
```

Python fallback:

```bash
pipx install git+https://github.com/danielalkurdi/matteros.git
```

See [docs/INSTALL.md](./docs/INSTALL.md) for additional installation notes.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

matteros init
matteros onboard
matteros auth login --client-id <your-app-client-id>
matteros llm doctor
matteros connectors list
matteros playbooks list
matteros run matteros/playbooks/daily_time_capture.yml --dry-run --input tests/fixtures/run_input.json
matteros audit verify --run-id <RUN_ID> --source both
```

## Onboarding

Guided setup:

```bash
matteros onboard
```

Non-interactive setup for CI/devcontainers:

```bash
matteros onboard --non-interactive --yes --skip-auth
```

Readiness status:

```bash
matteros onboard status
```

## Audit verification

```bash
matteros audit verify --run-id <RUN_ID> --source both
matteros audit verify --run-id <RUN_ID> --source db
```

- Success output starts with `audit verified:` and exits with code `0`.
- Verification failure output starts with `audit verification failed:` and exits with code `1`.
- Missing run events or invalid verify options exit with code `2`.

## Safety defaults

- Connectors are read-only by default.
- Side effects are allowed only in `apply` steps with explicit approval mode.
- Audit events are append-only and hash-chained.
- Audit chain integrity can be verified from SQLite and JSONL with `matteros audit verify`.
- Microsoft Graph access uses OAuth device-code login with cached refreshable tokens in `.matteros/auth/ms_graph_token.json`.
- LLM outputs are validated against versioned schema contracts (currently `time_entry_suggestions.v1`).
- Remote LLM providers are opt-in via `MATTEROS_ALLOW_REMOTE_MODELS=true` (default is local-only).

## LLM provider configuration

- `MATTEROS_MODEL_PROVIDER`:
  `local` (default), `openai`, `anthropic`
- `MATTEROS_ALLOW_REMOTE_MODELS`:
  must be `true` to allow `openai`/`anthropic`
- `MATTEROS_LLM_MODEL_ALLOWLIST`:
  optional comma-separated exact model names
- `MATTEROS_LLM_MAX_RETRIES`:
  retry attempts for retryable provider failures (default `2`)
- `MATTEROS_LLM_RETRY_BACKOFF_SECONDS`:
  exponential backoff base seconds (default `0.5`)
- `MATTEROS_LLM_TIMEOUT_SECONDS`:
  provider HTTP timeout in seconds (default `30`)
- OpenAI:
  `OPENAI_API_KEY`, optional `OPENAI_MODEL` and `OPENAI_BASE_URL`
- Anthropic:
  `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_VERSION`

## External Provider Contract Tests (VCR)

- Tests are skipped by default.
- Replay existing cassettes:
  `MATTEROS_RUN_EXTERNAL_TESTS=1 MATTEROS_VCR_RECORD_MODE=none pytest -q -m external`
- Record/update cassettes:
  `MATTEROS_RUN_EXTERNAL_TESTS=1 MATTEROS_VCR_RECORD_MODE=once pytest -q -m external`
- Set provider keys before recording:
  `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`

## License

AGPLv3 (`AGPL-3.0-only`).
