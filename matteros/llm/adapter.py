from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from time import monotonic
from typing import Any

from matteros.llm.errors import LLMConfigurationError, LLMProviderError
from matteros.llm.providers.anthropic import AnthropicProvider
from matteros.llm.providers.local import LocalProvider
from matteros.llm.providers.openai import OpenAIProvider


class LLMAdapter:
    def __init__(
        self,
        default_provider: str | None = None,
        *,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ):
        self.providers = {
            "local": LocalProvider(),
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
        }
        self.default_provider = default_provider or os.getenv("MATTEROS_MODEL_PROVIDER", "local")
        self.max_retries = max_retries if max_retries is not None else int(os.getenv("MATTEROS_LLM_MAX_RETRIES", "2"))
        self.retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else float(os.getenv("MATTEROS_LLM_RETRY_BACKOFF_SECONDS", "0.5"))
        )
        self.allow_remote_models = _truthy(os.getenv("MATTEROS_ALLOW_REMOTE_MODELS", "false"))
        self.model_allowlist = _split_csv(os.getenv("MATTEROS_LLM_MODEL_ALLOWLIST"))

    def run(
        self,
        *,
        task: str,
        payload: dict[str, Any],
        schema_name: str | None,
        provider_override: str | None = None,
    ) -> Any:
        result, _ = self.run_with_metadata(
            task=task,
            payload=payload,
            schema_name=schema_name,
            provider_override=provider_override,
        )
        return result

    def run_with_metadata(
        self,
        *,
        task: str,
        payload: dict[str, Any],
        schema_name: str | None,
        provider_override: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        provider_name = provider_override or self.default_provider
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"unknown model provider: {provider_name}")

        self._enforce_provider_policy(provider_name)
        model_name = self._provider_model_name(provider)
        self._enforce_model_allowlist(provider_name=provider_name, model_name=model_name)

        self._validate_untrusted_boundary(payload)
        started = monotonic()
        attempts = 0

        while True:
            attempts += 1
            try:
                result = provider.generate(task=task, payload=payload, schema_name=schema_name)
                elapsed_ms = int((monotonic() - started) * 1000)
                return (
                    result,
                    {
                        "provider": provider_name,
                        "model": model_name,
                        "attempts": attempts,
                        "latency_ms": elapsed_ms,
                    },
                )
            except LLMProviderError as exc:
                if not exc.retryable or attempts > self.max_retries:
                    raise
                sleep_for = self.retry_backoff_seconds * (2 ** (attempts - 1))
                if sleep_for > 0:
                    time.sleep(sleep_for)

    def _validate_untrusted_boundary(self, payload: dict[str, Any]) -> None:
        # Enforce data-only payload channel: do not permit instruction override fields.
        forbidden = {"system_prompt", "instructions", "tool_call"}
        overlap = forbidden.intersection(payload.keys())
        if overlap:
            keys = ", ".join(sorted(overlap))
            raise ValueError(f"untrusted payload attempted to set instruction fields: {keys}")

    def _enforce_provider_policy(self, provider_name: str) -> None:
        if provider_name == "local":
            return
        if not self.allow_remote_models:
            raise LLMConfigurationError(
                "remote model providers are disabled by default; set MATTEROS_ALLOW_REMOTE_MODELS=true to enable"
            )

    def _enforce_model_allowlist(self, *, provider_name: str, model_name: str) -> None:
        if provider_name == "local":
            return
        if not self.model_allowlist:
            return
        if model_name in self.model_allowlist:
            return
        allowed = ", ".join(self.model_allowlist)
        raise LLMConfigurationError(
            f"model '{model_name}' is not in MATTEROS_LLM_MODEL_ALLOWLIST ({allowed})"
        )

    def _provider_model_name(self, provider: Any) -> str:
        value = getattr(provider, "model_name", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "unknown"

    def render_payload_snapshot(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None) -> Sequence[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
