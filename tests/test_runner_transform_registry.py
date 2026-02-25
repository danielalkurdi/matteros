"""Tests for runner transform function dispatch."""

from __future__ import annotations

import pytest

from matteros.core.runner import _TRANSFORM_FUNCTIONS


def test_dispatch_known_transform() -> None:
    """cluster_activities works through dict dispatch."""
    fn = _TRANSFORM_FUNCTIONS.get("cluster_activities")
    assert fn is not None
    result = fn({"calendar_events": [], "sent_emails": []})
    assert isinstance(result, list)


def test_dispatch_unknown_transform_raises() -> None:
    """Unknown function name is not in the dispatch dict."""
    assert _TRANSFORM_FUNCTIONS.get("nonexistent") is None
