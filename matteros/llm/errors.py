from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for LLM-related runtime failures."""


class LLMConfigurationError(LLMError):
    """Raised when provider configuration or policy is invalid."""


class LLMProviderError(LLMError):
    """Raised for API/provider failures."""

    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class LLMAuthError(LLMProviderError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message, retryable=False, status_code=status_code)


class LLMRateLimitError(LLMProviderError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message, retryable=True, status_code=status_code)


class LLMTimeoutError(LLMProviderError):
    def __init__(self, message: str = "LLM request timed out"):
        super().__init__(message, retryable=True)


class LLMResponseFormatError(LLMProviderError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)
