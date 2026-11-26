"""
Ollama LLM provider for ProductSignal.

Local inference via Ollama's non-streaming /api/generate endpoint. All HTTP
handling is isolated here; the rest of the application only sees LLMResponse
objects and the LLMProviderError hierarchy. No retries, no model downloads,
no credentials: connection details come from configuration.
"""

import time
from typing import Optional

import requests

from .base import (
    LLMConnectionError,
    LLMProviderError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
)

# Ollama reports durations in nanoseconds; useful raw values are surfaced in
# metadata, while duration_seconds is measured client-side for comparability.
_METADATA_KEYS = ("done", "eval_count", "prompt_eval_count", "total_duration")


class OllamaProvider:
    """LLM provider backed by a local Ollama server."""

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 30.0):
        if not base_url or not str(base_url).strip():
            raise ValueError("OllamaProvider requires a non-empty base_url")
        if not model or not str(model).strip():
            raise ValueError("OllamaProvider requires a non-empty model name")
        if timeout_seconds is None or timeout_seconds <= 0:
            raise ValueError("OllamaProvider timeout_seconds must be positive")

        self._base_url = str(base_url).rstrip("/")
        self._model = str(model)
        self._timeout_seconds = float(timeout_seconds)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            payload["options"] = options

        timeout = self._timeout_seconds if timeout_seconds is None else timeout_seconds

        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(
                f"Ollama request timed out after {timeout}s"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(
                f"Could not connect to Ollama at {self._base_url}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            # Keep the exception type only; message may contain request details.
            raise LLMProviderError(
                f"Ollama request failed: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            # Status code and provider identity only. The body is deliberately
            # excluded: error responses are server-controlled and can echo the
            # request (prompt/customer feedback), headers, or internal details.
            raise LLMResponseError(
                f"Ollama returned HTTP {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "Ollama returned a response that is not valid JSON"
            ) from exc

        if not isinstance(data, dict) or not isinstance(data.get("response"), str):
            raise LLMResponseError(
                "Ollama response is missing the 'response' text field"
            )

        duration = time.perf_counter() - started
        return LLMResponse(
            text=data["response"],
            provider=self.provider_name,
            model=data.get("model") or self._model,
            duration_seconds=duration,
            metadata={key: data[key] for key in _METADATA_KEYS if key in data},
        )
