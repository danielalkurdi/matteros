# Connector Specifications (MVP)

## ms_graph_mail

- Mode: read
- Operation: `sent_emails`
- Required params: optional `start`, `end`, or `mock_file`
- Output: list of sent-message metadata
- Auth: bearer token from `MATTEROS_MS_GRAPH_TOKEN` or cached OAuth token (`matteros auth login`)

## ms_graph_calendar

- Mode: read
- Operation: `events`
- Required params: `start`, `end` or `mock_file`
- Output: list of calendar event metadata
- Auth: bearer token from `MATTEROS_MS_GRAPH_TOKEN` or cached OAuth token (`matteros auth login`)

## filesystem

- Mode: read
- Operation: `activity_metadata`
- Required params: `root_path`
- Output: list of file metadata records

## csv_export

- Mode: write
- Operation: `export_time_entries`
- Required params: `output_path`
- Output: write summary (`rows_written`, `output_path`)
