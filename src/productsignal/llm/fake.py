"""
Deterministic fake LLM provider for ProductSignal tests.

Implements the same contract as OllamaProvider with no network I/O and no
randomness: responses come from a configured queue and every request is
recorded for assertions. Queue entries may be strings (returned as the
response text) or Exception instances (raised in sequence).
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

from .base import LLMProviderError, LLMResponse


@dataclass(frozen=True)
class RecordedRequest:
    """One captured generate() call, for test assertions."""

    prompt: str
    system_prompt: Optional[str]
    temperature: Optional[float]
    timeout_seconds: Optional[float]


class FakeProvider:
    """In-memory provider with scripted responses and request recording."""

    def __init__(
        self,
        model: str = "fake-model",
        responses: Optional[Sequence[Union[str, Exception]]] = None,
    ):
        if not model:
            raise ValueError("FakeProvider requires a non-empty model name")
        self._model = model
        self._queue: List[Union[str, Exception]] = list(responses) if responses else []
        self.recorded_requests: List[RecordedRequest] = []

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return self._model

    def configure(self, *responses: Union[str, Exception]) -> None:
        """Replace the scripted response queue."""
        self._queue = list(responses)

    @property
    def remaining_responses(self) -> int:
        return len(self._queue)

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
    ) -> LLMResponse:
        self.recorded_requests.append(
            RecordedRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
        )

        if not self._queue:
            raise LLMProviderError(
                "FakeProvider has no configured responses left; "
                "call configure(*responses) to script more"
            )

        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item

        return LLMResponse(
            text=item,
            provider=self.provider_name,
            model=self._model,
            duration_seconds=0.0,
            metadata={"simulated": True},
        )
