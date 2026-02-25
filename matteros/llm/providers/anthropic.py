from __future__ import annotations

import json
import os
from typing import Any

import httpx

from matteros.core.schemas import schema_json
from matteros.llm.errors import (
    LLMAuthError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseFormatError,
    LLMTimeoutError,
)
from matteros.llm.json_utils import parse_json_object
from matteros.llm.tasks import get_registry


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.timeout_seconds = float(os.getenv("MATTEROS_LLM_TIMEOUT_SECONDS", "30"))
        self.model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self.api_version = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

    def generate(self, *, task: str, payload: dict[str, Any], schema_name: str | None) -> Any:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is not configured")

        try:
            spec = get_registry().get(task)
        except KeyError as exc:
            raise LLMConfigurationError(str(exc)) from exc

        if spec.schema_name and not schema_name:
            raise LLMConfigurationError(f"schema_name is required for task '{task}'")

        schema = schema_json(schema_name) if schema_name else None
        system_content = spec.system_prompt
        user_content = spec.user_prompt_template.replace(
            "{{payload}}", json.dumps(payload, ensure_ascii=True, sort_keys=True)
        )
        if schema:
            user_content = (
                f"Schema:\n{json.dumps(schema, ensure_ascii=True, sort_keys=True)}\n"
                + user_content
            )

        request_payload = {
            "model": self.model_name,
            "max_tokens": 2048,
            "temperature": 0,
            "system": system_content,
            "messages": [
                {
                    "role": "user",
                    "content": user_content,
                }
            ],
        }

        response = self._post_json(
            path="/v1/messages",
            body=request_payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": self.api_version,
                "content-type": "application/json",
            },
        )

        content = self._extract_text_content(response)
        return parse_json_object(content)

    def _post_json(self, *, path: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"anthropic request failed: {exc}", retryable=True) from exc

        payload = self._decode_json(response)
        if response.status_code >= 400:
            raise self._http_error(response.status_code, payload, provider_name="anthropic")

        return payload

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError("anthropic response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise LLMResponseFormatError("anthropic response JSON root must be an object")
        return payload

    def _http_error(self, status: int, payload: dict[str, Any], *, provider_name: str) -> LLMProviderError:
        message = self._error_message(payload)
        if status in {401, 403}:
            return LLMAuthError(f"{provider_name} authentication failed: {message}", status_code=status)
        if status == 429:
            return LLMRateLimitError(f"{provider_name} rate limited: {message}", status_code=status)

        retryable = status >= 500
        return LLMProviderError(
            f"{provider_name} request failed ({status}): {message}",
            retryable=retryable,
            status_code=status,
        )

    def _error_message(self, payload: dict[str, Any]) -> str:
        err = payload.get("error")
        if isinstance(err, dict):
            detail = err.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        if isinstance(err, str) and err.strip():
            return err.strip()
        return "unknown error"

    def _extract_text_content(self, payload: dict[str, Any]) -> str:
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        return text

        # Allow fallback for alternate SDK style payloads.
        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return output_text

        raise LLMResponseFormatError("anthropic response missing text content")
