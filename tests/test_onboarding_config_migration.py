from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from matteros.cli import app
from matteros.core.config import load_config

runner = CliRunner()


def test_onboard_migrates_legacy_config_and_creates_backup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    legacy = home / "config.yml"
    legacy.write_text(
        """
model_provider: openai
log_level: debug
ms_graph_tenant_id: my-tenant
ms_graph_scopes: offline_access User.Read
""",
        encoding="utf-8",
    )

    result = runner.invoke(
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

    assert result.exit_code == 0
    assert "migrated legacy config" in result.stdout

    backups = sorted(home.glob("config.yml.bak.*"))
    assert backups, "expected legacy config backup file"

    loaded = load_config(path=home / "config.yml", home=home)
    cfg = loaded.config
    assert cfg.llm.provider == "openai"
    assert cfg.log_level == "debug"
    assert cfg.ms_graph.tenant_id == "my-tenant"
    assert cfg.ms_graph.scopes == "offline_access User.Read"
