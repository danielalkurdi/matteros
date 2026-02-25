"""Tests that providers dispatch tasks via the registry."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from matteros.llm.errors import LLMConfigurationError
from matteros.llm.providers.local import LocalProvider


class TestLocalProvider:
    def test_local_dispatches_via_registry(self) -> None:
        """LocalProvider handles draft_time_entries through registry."""
        provider = LocalProvider()
        result = provider.generate(
            task="draft_time_entries",
            payload={"clusters": []},
            schema_name="time_entry_suggestions.v1",
        )
        assert result["schema_version"] == "time_entry_suggestions.v1"
        assert isinstance(result["suggestions"], list)

    def test_local_unknown_task_raises(self) -> None:
        provider = LocalProvider()
        with pytest.raises(KeyError, match="unknown task"):
            provider.generate(task="nonexistent_task", payload={}, schema_name=None)

    def test_local_narrative_polish(self) -> None:
        """LocalProvider dispatches narrative_polish via registry."""
        provider = LocalProvider()
        result = provider.generate(
            task="narrative_polish",
            payload={"narrative": "hello hello world"},
            schema_name=None,
        )
        assert "polished_narrative" in result

    def test_local_classify_matter(self) -> None:
        provider = LocalProvider()
        result = provider.generate(
            task="classify_matter",
            payload={"texts": ["Working on MAT-1234"]},
            schema_name=None,
        )
        assert result["matter_id"] != "UNASSIGNED"
        assert result["confidence"] == 0.9

    def test_local_weekly_digest(self) -> None:
        provider = LocalProvider()
        result = provider.generate(
            task="weekly_digest",
            payload={"entries": [{"matter_id": "MAT-1", "duration_minutes": 30}]},
            schema_name=None,
        )
        assert "markdown" in result


class TestAnthropicProviderRegistry:
    def test_anthropic_dispatches_via_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        from matteros.llm.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider()

        mock_response = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "schema_version": "time_entry_suggestions.v1",
                        "suggestions": [],
                    }),
                }
            ]
        }

        with patch.object(provider, "_post_json", return_value=mock_response):
            result = provider.generate(
                task="draft_time_entries",
                payload={"clusters": []},
                schema_name="time_entry_suggestions.v1",
            )
        assert isinstance(result, dict)

    def test_anthropic_unknown_task_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        from matteros.llm.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        with pytest.raises(LLMConfigurationError, match="unknown task"):
            provider.generate(task="nonexistent_task", payload={}, schema_name=None)


class TestOpenAIProviderRegistry:
    def test_openai_dispatches_via_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        from matteros.llm.providers.openai import OpenAIProvider

        provider = OpenAIProvider()

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "schema_version": "time_entry_suggestions.v1",
                            "suggestions": [],
                        }),
                    }
                }
            ]
        }

        with patch.object(provider, "_post_json", return_value=mock_response):
            result = provider.generate(
                task="draft_time_entries",
                payload={"clusters": []},
                schema_name="time_entry_suggestions.v1",
            )
        assert isinstance(result, dict)

    def test_openai_unknown_task_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        from matteros.llm.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(LLMConfigurationError, match="unknown task"):
            provider.generate(task="nonexistent_task", payload={}, schema_name=None)
