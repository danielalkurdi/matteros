# Connector Specifications

MatterOS connectors expose a manifest with:

- `connector_id`
- `default_mode` (`read` or `write`)
- operation map (`operation -> mode`)

Use this to inspect your active registry at runtime:

```bash
matteros connectors list
```

## Core connectors

### `ms_graph_mail`

- Default mode: `read`
- Operations:
  - `sent_emails` (`read`)
- Typical params:
  - `start`, `end` (ISO datetimes)
  - optional `mock_file`
- Auth:
  - OAuth device-code token cache (`matteros auth login`)

### `ms_graph_calendar`

- Default mode: `read`
- Operations:
  - `events` (`read`)
- Typical params:
  - `start`, `end` (ISO datetimes)
  - optional `mock_file`
- Auth:
  - OAuth device-code token cache (`matteros auth login`)

### `filesystem`

- Default mode: `read`
- Operations:
  - `activity_metadata` (`read`)
- Typical params:
  - `root_path`
  - optional `start`, `end`, `max_files`

### `csv_export`

- Default mode: `write`
- Operations:
  - `export_time_entries` (`write`)
- Typical params:
  - `output_path`

## Optional built-in connectors

These are registered when required env vars are present.

### `slack`

- Default mode: `read`
- Operations:
  - `messages` (`read`)
  - `post_summary` (`write`)
- Env:
  - `MATTEROS_SLACK_TOKEN`

### `jira`

- Default mode: `read`
- Operations:
  - `worklogs` (`read`)
  - `issues` (`read`)
  - `log_time` (`write`)
- Env:
  - `MATTEROS_JIRA_TOKEN`
  - `MATTEROS_JIRA_URL`

### `github`

- Default mode: `read`
- Operations:
  - `commits` (`read`)
  - `prs` (`read`)
- Env:
  - `MATTEROS_GITHUB_TOKEN`

### `ical`

- Default mode: `read`
- Operations:
  - `events` (`read`)
- No auth required (local `.ics` parsing)

## Plugin connectors

MatterOS can load custom connectors from:

- installed Python entry points (`matteros.connectors`)
- local plugin files/packages in `~/.matteros/plugins` (or `<home>/plugins`)

Plugin connectors must provide a valid `Connector` implementation and manifest.

At startup, plugins are discovered and registered unless their `connector_id` conflicts with an already-registered connector.
