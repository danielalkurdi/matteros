from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from matteros.cli import app
from matteros.core.config import load_config

runner = CliRunner()


def test_onboard_non_interactive_creates_config_and_smoke_run(tmp_path: Path) -> None:
    home = tmp_path / "home"

    result = runner.invoke(
        app,
        [
            "onboard",
            "--non-interactive",
            "--yes",
            "--skip-auth",
            "--home",
            str(home),
        ],
    )

    assert result.exit_code == 0
    assert "onboarding complete" in result.stdout

    loaded = load_config(path=home / "config.yml", home=home)
    cfg = loaded.config
    assert loaded.existed
    assert cfg.onboarding.completed_at is not None
    assert cfg.onboarding.last_smoke_test_status == "passed"
    assert cfg.onboarding.last_smoke_test_run_id is not None


def test_onboard_status_shows_pending_auth_when_skipped(tmp_path: Path) -> None:
    home = tmp_path / "home"

    setup = runner.invoke(
        app,
        [
            "onboard",
            "--non-interactive",
            "--yes",
            "--skip-auth",
            "--skip-smoke-test",
            "--home",
            str(home),
        ],
    )
    assert setup.exit_code == 0

    result = runner.invoke(app, ["onboard", "status", "--home", str(home)])
    assert result.exit_code == 1
    assert "auth_ready: False" in result.stdout


def test_onboard_status_passes_with_valid_auth_and_smoke(tmp_path: Path) -> None:
    home = tmp_path / "home"

    setup = runner.invoke(
        app,
        [
            "onboard",
            "--non-interactive",
            "--yes",
            "--skip-auth",
            "--home",
            str(home),
        ],
    )
    assert setup.exit_code == 0

    # Simulate valid token cache and clear auth_pending flag.
    token_path = home / "auth" / "ms_graph_token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(
            {
                "access_token": "token",
                "refresh_token": "refresh",
                "expires_at": 32503680000,
                "tenant_id": "common",
                "client_id": "test-client",
                "scope": "offline_access User.Read Mail.Read Calendars.Read",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(path=home / "config.yml", home=home)
    cfg = loaded.config
    cfg.ms_graph.auth_pending = False
    from matteros.core.config import save_config_atomic

    save_config_atomic(config=cfg, path=home / "config.yml")

    result = runner.invoke(app, ["onboard", "status", "--home", str(home)])
    assert result.exit_code == 0
    assert "auth_ready: True" in result.stdout
    assert "smoke_test_passed: True" in result.stdout
