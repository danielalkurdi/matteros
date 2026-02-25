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


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = float(os.getenv("MATTEROS_LLM_TIMEOUT_SECONDS", "30"))
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def generate(self, *, task: str, payload: dict[str, Any], schema_name: str | None) -> Any:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is not configured")

        if task != "draft_time_entries":
            raise LLMConfigurationError(f"unsupported openai task: {task}")
        if not schema_name:
            raise LLMConfigurationError("schema_name is required for openai structured output")

        request_payload = self._build_request_payload(task=task, payload=payload, schema_name=schema_name)
        response = self._post_json(
            path="/chat/completions",
            body=request_payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        content = self._extract_content(response)
        return parse_json_object(content)

    def _build_request_payload(
        self,
        *,
        task: str,
        payload: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        response_schema = schema_json(schema_name)

        return {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a legal ops assistant. Return only valid JSON that matches the schema. "
                        "Do not include markdown or explanatory text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n"
                        "Payload:\n"
                        f"{json.dumps(payload, ensure_ascii=True, sort_keys=True)}"
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "matteros_structured_output",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        }

    def _post_json(self, *, path: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"openai request failed: {exc}", retryable=True) from exc

        payload = self._decode_json(response)
        if response.status_code >= 400:
            raise self._http_error(response.status_code, payload, provider_name="openai")

        return payload

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError("openai response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise LLMResponseFormatError("openai response JSON root must be an object")
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

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                return str(part["text"])

        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return output_text

        raise LLMResponseFormatError("openai response missing textual content")
