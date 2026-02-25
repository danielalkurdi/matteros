# Installation

This guide gives you three install paths:

- fast start with Homebrew
- full-feature source install (recommended)
- lightweight CLI install with pipx

## Option 1: Homebrew

```bash
brew tap danielalkurdi/matteros
brew install matteros
```

Then initialize:

```bash
matteros init
matteros onboard
```

## Option 2: Source install (recommended)

Use this if you want the full stack (web, tui, daemon, team, tests).

```bash
git clone https://github.com/danielalkurdi/matteros.git
cd matteros
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all,dev]'
```

Verify:

```bash
matteros --help
```

## Option 3: pipx fallback

```bash
pipx install git+https://github.com/danielalkurdi/matteros.git
```

This is best for baseline CLI usage. For optional interfaces, use source install or install extras in a virtualenv.

## Onboarding

Interactive:

```bash
matteros onboard
matteros onboard status
```

Non-interactive (CI/devcontainer):

```bash
matteros onboard --non-interactive --yes --skip-auth
```

## Optional interfaces

If a command says dependencies are missing, install the relevant extras:

```bash
pip install -e '.[web]'
pip install -e '.[tui]'
pip install -e '.[daemon]'
pip install -e '.[team]'
```

Or install all at once:

```bash
pip install -e '.[all]'
```

## Web dashboard note

`matteros web` prints a bootstrap URL that includes an access token query parameter.
Open that URL first and keep it private.

## Quick smoke test

```bash
matteros init
matteros connectors list
matteros playbooks list
matteros run playbooks/daily_time_capture.yml --dry-run --input tests/fixtures/run_input.json
```
