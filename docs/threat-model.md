# Threat Model (MVP)

## Assets

- Matter metadata and activity timelines
- Draft billing narratives
- Approval decisions and audit logs

## Trust boundaries

- Local CLI runtime
- External Microsoft Graph API
- Local filesystem scanner
- Optional external LLM providers

## Primary threats

- Prompt injection via email/document text
- Over-privileged connectors causing unauthorized writes
- Tampering with run history or approvals
- Data exfiltration via accidental provider defaults

## MVP mitigations

- Untrusted connector payloads handled as data channel only
- Connector manifests with explicit read/write operations
- Side effects constrained to `apply` steps after approval
- Audit events hash-chained and append-only
- Local provider default; cloud providers are opt-in
