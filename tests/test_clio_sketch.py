"""Tests for Clio and PracticePanther sketch connectors."""

from __future__ import annotations

import pytest

from matteros.connectors.clio_sketch import ClioConnector
from matteros.connectors.practice_panther_sketch import PracticePantherConnector
from matteros.core.types import PermissionMode


def test_clio_manifest_valid() -> None:
    connector = ClioConnector()
    assert connector.manifest.connector_id == "clio"
    assert "matters" in connector.manifest.operations
    assert "time_entries" in connector.manifest.operations
    assert "create_time_entry" in connector.manifest.operations
    assert connector.manifest.operations["create_time_entry"] == PermissionMode.WRITE


def test_clio_operations_raise_not_implemented() -> None:
    connector = ClioConnector()
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        connector.read("matters", {}, {})
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        connector.write("create_time_entry", {}, {}, {})


def test_practice_panther_manifest_valid() -> None:
    connector = PracticePantherConnector()
    assert connector.manifest.connector_id == "practice_panther"
    assert "matters" in connector.manifest.operations
    assert connector.manifest.operations["create_time_entry"] == PermissionMode.WRITE


def test_practice_panther_operations_raise_not_implemented() -> None:
    connector = PracticePantherConnector()
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        connector.read("time_entries", {}, {})
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        connector.write("create_time_entry", {}, {}, {})
