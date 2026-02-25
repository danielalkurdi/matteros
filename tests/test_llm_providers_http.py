from __future__ import annotations

import pytest

from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1
from matteros.llm.errors import LLMResponseFormatError
from matteros.llm.providers.anthropic import AnthropicProvider
from matteros.llm.providers.openai import OpenAIProvider


def test_openai_provider_parses_chat_completion_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    def fake_post_json(*, path: str, body: dict, headers: dict):
        assert path == "/chat/completions"
        assert "response_format" in body
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"schema_version":"time_entry_suggestions.v1","suggestions":[]}'
                    }
                }
            ]
        }

    provider._post_json = fake_post_json  # type: ignore[method-assign]
    result = provider.generate(
        task="draft_time_entries",
        payload={"clusters": []},
        schema_name=SCHEMA_TIME_ENTRY_V1,
    )

    assert result["schema_version"] == SCHEMA_TIME_ENTRY_V1


def test_anthropic_provider_parses_text_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider()

    def fake_post_json(*, path: str, body: dict, headers: dict):
        assert path == "/v1/messages"
        return {
            "content": [
                {
                    "type": "text",
                    "text": "```json\n{\"schema_version\":\"time_entry_suggestions.v1\",\"suggestions\":[]}\n```",
                }
            ]
        }

    provider._post_json = fake_post_json  # type: ignore[method-assign]
    result = provider.generate(
        task="draft_time_entries",
        payload={"clusters": []},
        schema_name=SCHEMA_TIME_ENTRY_V1,
    )

    assert result["schema_version"] == SCHEMA_TIME_ENTRY_V1


def test_openai_provider_rejects_non_json_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    provider._post_json = lambda **_: {  # type: ignore[method-assign]
        "choices": [{"message": {"content": "not json"}}]
    }

    with pytest.raises(LLMResponseFormatError):
        provider.generate(
            task="draft_time_entries",
            payload={"clusters": []},
            schema_name=SCHEMA_TIME_ENTRY_V1,
        )
