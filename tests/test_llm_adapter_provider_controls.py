from __future__ import annotations

import pytest

from matteros.core.schemas import SCHEMA_TIME_ENTRY_V1
from matteros.llm import LLMAdapter
from matteros.llm.errors import LLMConfigurationError, LLMTimeoutError


class _FakeProvider:
    def __init__(self, *, model_name: str = "fake-model") -> None:
        self.model_name = model_name

    def generate(self, *, task: str, payload: dict, schema_name: str | None):  # type: ignore[override]
        return {
            "schema_version": schema_name or SCHEMA_TIME_ENTRY_V1,
            "suggestions": [],
        }


def test_remote_provider_blocked_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATTEROS_ALLOW_REMOTE_MODELS", raising=False)
    adapter = LLMAdapter(default_provider="openai")
    adapter.providers["openai"] = _FakeProvider(model_name="gpt-4.1-mini")

    with pytest.raises(LLMConfigurationError):
        adapter.run(
            task="draft_time_entries",
            payload={"clusters": []},
            schema_name=SCHEMA_TIME_ENTRY_V1,
        )


def test_remote_provider_allowed_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTEROS_ALLOW_REMOTE_MODELS", "true")
    adapter = LLMAdapter(default_provider="openai")
    adapter.providers["openai"] = _FakeProvider(model_name="gpt-4.1-mini")

    result, metadata = adapter.run_with_metadata(
        task="draft_time_entries",
        payload={"clusters": []},
        schema_name=SCHEMA_TIME_ENTRY_V1,
    )

    assert result["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert metadata["provider"] == "openai"
    assert metadata["model"] == "gpt-4.1-mini"


def test_model_allowlist_rejects_non_allowed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTEROS_ALLOW_REMOTE_MODELS", "true")
    monkeypatch.setenv("MATTEROS_LLM_MODEL_ALLOWLIST", "gpt-4.1-mini")

    adapter = LLMAdapter(default_provider="openai")
    adapter.providers["openai"] = _FakeProvider(model_name="gpt-4.1-nano")

    with pytest.raises(LLMConfigurationError):
        adapter.run(
            task="draft_time_entries",
            payload={"clusters": []},
            schema_name=SCHEMA_TIME_ENTRY_V1,
        )


def test_adapter_retries_retryable_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTEROS_ALLOW_REMOTE_MODELS", "true")

    class _FlakyProvider:
        model_name = "gpt-4.1-mini"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, *, task: str, payload: dict, schema_name: str | None):  # type: ignore[override]
            self.calls += 1
            if self.calls == 1:
                raise LLMTimeoutError()
            return {"schema_version": schema_name, "suggestions": []}

    provider = _FlakyProvider()
    adapter = LLMAdapter(default_provider="openai", max_retries=1, retry_backoff_seconds=0)
    adapter.providers["openai"] = provider

    result, metadata = adapter.run_with_metadata(
        task="draft_time_entries",
        payload={"clusters": []},
        schema_name=SCHEMA_TIME_ENTRY_V1,
    )

    assert result["schema_version"] == SCHEMA_TIME_ENTRY_V1
    assert provider.calls == 2
    assert metadata["attempts"] == 2
