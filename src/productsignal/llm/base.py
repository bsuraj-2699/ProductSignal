"""
LLM provider contract for ProductSignal.

LLMProvider is a typing.Protocol: any object with the same properties and
generate() signature is a valid provider, with no inheritance requirement.
LLMResponse is the standard result object every provider returns. Failures
are expressed through the LLMProviderError hierarchy so downstream code can
distinguish connection problems, timeouts, and bad provider responses without
knowing provider internals.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


class LLMProviderError(Exception):
    """Base class for all LLM provider failures."""


class LLMConnectionError(LLMProviderError):
    """The provider endpoint could not be reached."""


class LLMTimeoutError(LLMProviderError):
    """The provider did not answer within the configured timeout."""


class LLMResponseError(LLMProviderError):
    """The provider answered with an HTTP error or a malformed payload."""


@dataclass(frozen=True)
class LLMResponse:
    """
    Standard provider response.

    `text` is the raw generated output exactly as returned by the provider —
    it is never parsed, normalized, or repaired here. Structured-output
    parsing and validation belong to the classification pipeline.
    """

    text: str
    provider: str
    model: str
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Contract every LLM backend must satisfy."""

    @property
    def provider_name(self) -> str:
        """Provider identity (e.g. 'ollama', 'fake')."""
        ...

    @property
    def model_name(self) -> str:
        """Model identity as configured for this provider."""
        ...

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
    ) -> LLMResponse:
        """
        Submit one inference request and return the raw generated text.

        Args:
            prompt: The user prompt text.
            system_prompt: Optional system-level instruction.
            temperature: Optional per-request generation temperature override.
            timeout_seconds: Optional per-request timeout override; the
                provider's configured timeout applies when None.

        Returns:
            An LLMResponse; raw text is passed through unmodified.

        Raises:
            LLMConnectionError: The endpoint could not be reached.
            LLMTimeoutError: The request exceeded its timeout.
            LLMResponseError: HTTP error status or malformed API payload.
            LLMProviderError: Any other provider failure.
        """
        ...
