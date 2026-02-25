"""Tests for the ConnectorsConfig addition."""

from __future__ import annotations

from pathlib import Path

from matteros.core.config import ConnectorsConfig, MatterOSConfig, default_config


def test_connectors_config_defaults() -> None:
    cfg = ConnectorsConfig()
    assert cfg.slack_enabled is False
    assert cfg.jira_enabled is False
    assert cfg.github_enabled is False
    assert cfg.ical_enabled is True


def test_matteros_config_includes_connectors(tmp_path: Path) -> None:
    cfg = default_config(home=tmp_path)
    assert hasattr(cfg, "connectors")
    assert isinstance(cfg.connectors, ConnectorsConfig)
