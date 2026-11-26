"""
LLM provider abstraction for ProductSignal.

Defines the provider contract shared by all LLM backends, the standard
response object, and provider-failure exceptions. The abstraction is
deliberately small: it submits prompts and returns raw generated text. It
knows nothing about classification, taxonomy validation, persistence,
evidence grounding, or retries — those belong to the classification pipeline.

Providers:
    FakeProvider  — deterministic, in-memory, for tests
    OllamaProvider — local inference via Ollama's /api/generate endpoint
"""

from ..config import ProviderConfig
from .base import (
    LLMConnectionError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
)
from .fake import FakeProvider
from .ollama import OllamaProvider

__all__ = [
    "LLMConnectionError",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "LLMResponseError",
    "LLMTimeoutError",
    "FakeProvider",
    "OllamaProvider",
    "create_provider",
]


def create_provider(config: ProviderConfig) -> LLMProvider:
    """
    Build an LLM provider from configuration.

    Raises:
        ValueError: If the configured provider name has no implementation.
    """
    if config.name == "ollama":
        return OllamaProvider(
            base_url=config.base_url,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
        )
    if config.name == "fake":
        return FakeProvider(model=config.model)
    raise ValueError(
        f"No implementation for provider {config.name!r}; "
        f"supported providers: 'ollama', 'fake'"
    )
