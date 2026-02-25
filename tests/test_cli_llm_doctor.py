from __future__ import annotations

from typer.testing import CliRunner

from matteros.cli import app

runner = CliRunner()


def test_llm_doctor_local_ok(monkeypatch) -> None:
    monkeypatch.delenv("MATTEROS_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("MATTEROS_ALLOW_REMOTE_MODELS", raising=False)

    result = runner.invoke(app, ["llm", "doctor"])

    assert result.exit_code == 0
    assert "provider: local" in result.stdout
    assert "llm doctor: OK" in result.stdout


def test_llm_doctor_remote_blocked_by_default(monkeypatch) -> None:
    monkeypatch.setenv("MATTEROS_MODEL_PROVIDER", "openai")
    monkeypatch.delenv("MATTEROS_ALLOW_REMOTE_MODELS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = runner.invoke(app, ["llm", "doctor"])

    assert result.exit_code == 1
    assert "llm doctor: FAILED" in result.stdout
    assert "remote providers are disabled" in result.stdout


def test_llm_doctor_remote_enabled_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("MATTEROS_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MATTEROS_ALLOW_REMOTE_MODELS", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = runner.invoke(app, ["llm", "doctor"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY is not configured" in result.stdout
