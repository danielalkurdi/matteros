# Threat Model (Current)

## Assets

- Matter metadata and activity timelines
- Draft time entries and narratives
- Approval decisions and reviewer actions
- Audit trail integrity (SQLite + JSONL)
- OAuth credentials and API tokens

## Trust boundaries

- Local MatterOS runtime (CLI/TUI/Web/daemon)
- Connector boundaries (Microsoft Graph, Slack, Jira, GitHub, filesystem, iCal)
- Optional remote LLM providers
- Plugin connector loading path (`~/.matteros/plugins` / `<home>/plugins`)

## Primary threats

- Prompt injection via emails/docs/calendar text
- Over-privileged or malicious connector/plugin behavior
- Unauthorized writes without operator review
- Audit trail tampering or replay gaps
- Token leakage from mis-handled web bootstrap links

## Mitigations in place

- Connector manifests with explicit operation permissions
- Policy checks for connector declarations + operation validity
- Side effects constrained to `apply` steps with approval gating
- Audit events hash-chained and verifiable by CLI
- Local provider default; remote providers require explicit opt-in
- Web middleware requires token-based access
- Plugin ID collision prevention at registry time

## Residual risks

- Local plugin code runs with process privileges if loaded
- Operator error in approving low-quality suggestions
- Secret management remains environment/config dependent
