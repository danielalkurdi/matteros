# Security Policy

## Supported versions

MatterOS is pre-1.0. Security fixes target the latest `main` branch.

## Reporting a vulnerability

Please report vulnerabilities privately to project maintainers before public disclosure.
Include:
- Reproduction steps
- Impact scope
- Suggested mitigation (if known)

## Security posture for MVP

- Least-privilege connector manifests
- Read-only defaults for data connectors
- Human-in-the-loop approval gates for side effects
- Append-only audit logging with hash chain
- Structured output validation for all model-generated data
- Untrusted-input handling for connector payloads to mitigate prompt injection risk
