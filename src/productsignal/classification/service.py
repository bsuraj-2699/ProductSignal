"""
Single-feedback classification service for ProductSignal.

Orchestrates one classification operation end to end:

    prepare_feedback -> build_classification_prompt -> provider.generate()
    -> strict JSON parse -> ClassificationCreate validation

Deliberately limited to a single feedback record per invocation. There are no
retries, no evidence substring verification (Step 3.1.4c), no attempt
persistence, no database writes, and no UI here. Failures surface as typed
exceptions so a later pipeline stage can orchestrate retries and record
failure attempts. Provider failures propagate through the existing
LLMProviderError hierarchy unchanged.

Evidence quotes are only structurally validated (EvidenceQuote model).
Whether a quote is grounded in the original feedback text is NOT checked at
this stage.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import ValidationError

from ..config import ProductVibe
from ..llm.base import LLMProvider
from ..models.classification import ClassificationCreate, validate_classification_dict
from ..product_context.repository import ProductContext
from .preprocessing import prepare_feedback
from .prompting import FEEDBACK_CLOSE, build_classification_prompt


class ClassificationError(Exception):
    """Base class for classification pipeline failures."""


class UnusableFeedbackError(ClassificationError):
    """
    Feedback cannot be sent for inference at all: it is empty, exceeds the
    configured length, or contains the reserved prompt delimiter. Handle it
    with a deterministic fallback instead of a model call.
    """


class InvalidResponseError(ClassificationError):
    """
    The model response is not a usable JSON object under the prompt contract:
    malformed JSON, an empty response, a non-object top level, duplicate
    keys, non-standard constants, or fenced/prose-wrapped output.
    """


class ClassificationValidationError(ClassificationError):
    """The parsed JSON does not satisfy the classification schema."""


class TaxonomyValidationError(ClassificationValidationError):
    """The model named a primary/secondary category outside the active taxonomy."""


# Exactly the fields the prompt's OUTPUT CONTRACT lets the model supply.
# Anything else in the response — in particular persistence metadata — is
# rejected rather than ignored.
_LLM_OUTPUT_FIELDS = frozenset({
    "primary_category",
    "secondary_category",
    "sentiment",
    "severity",
    "customer_intent",
    "summary",
    "confidence",
    "needs_review",
    "evidence_quotes",
    "classification_reasoning",
    "mentioned_feature",
    "is_actionable",
})
_REQUIRED_LLM_FIELDS = frozenset({"primary_category", "sentiment", "severity", "summary"})
_APPLICATION_FIELDS = frozenset({
    "feedback_id", "product_id", "model_name", "model_version",
    "prompt_version", "classification_status", "error_note",
})
_TAXONOMY_FIELD_NAMES = frozenset({"primary_category", "secondary_category"})


@dataclass(frozen=True)
class ClassificationResult:
    """
    Outcome of one successful single-feedback classification.

    `classification` is fully validated and carries the application-controlled
    metadata (ids, model identity, prompt version, active status). The
    remaining fields repeat identity for convenient access and carry
    non-sensitive inference metadata (duration, provider-reported counters).
    """

    classification: ClassificationCreate
    feedback_id: int
    product_id: int
    provider_name: str
    model_name: str
    prompt_version: str
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class _DuplicateKeyError(ValueError):
    pass


def _object_pairs_no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        obj[key] = value
    return obj


def _reject_non_standard_constant(name: str) -> None:
    raise ValueError(f"non-standard JSON constant {name} is not permitted")


def parse_model_json(text: str) -> Dict[str, Any]:
    """
    Parse raw model output as a strict JSON object.

    No repair of any kind: markdown fences, surrounding prose, trailing
    commentary, duplicate keys, and NaN/Infinity constants all make the
    response invalid. The response text itself is never included in error
    messages.

    Raises:
        InvalidResponseError: For every parse-level failure.
    """
    if not isinstance(text, str):
        raise InvalidResponseError("model response is not text")
    if not text.strip():
        raise InvalidResponseError("model response is empty")

    try:
        data = json.loads(
            text,
            object_pairs_hook=_object_pairs_no_duplicates,
            parse_constant=_reject_non_standard_constant,
        )
    except json.JSONDecodeError as exc:
        raise InvalidResponseError(
            f"model response is not valid JSON ({exc.msg} at position {exc.pos})"
        ) from exc
    except (_DuplicateKeyError, ValueError) as exc:
        raise InvalidResponseError(f"model response rejected: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidResponseError(
            f"model response must be a JSON object, got {type(data).__name__}"
        )
    return data


def _reject_application_controlled_fields(data: Dict[str, Any]) -> None:
    attempted = sorted(_APPLICATION_FIELDS & data.keys())
    if attempted:
        raise ClassificationValidationError(
            "model response attempted to set application-controlled field(s): "
            + ", ".join(attempted)
        )


def _reject_unexpected_fields(data: Dict[str, Any]) -> None:
    unexpected = sorted(data.keys() - _LLM_OUTPUT_FIELDS)
    if unexpected:
        raise ClassificationValidationError(
            "unexpected field(s) in model response: "
            + ", ".join(repr(name) for name in unexpected)
        )


def _reject_missing_fields(data: Dict[str, Any]) -> None:
    missing = sorted(_REQUIRED_LLM_FIELDS - data.keys())
    if missing:
        raise ClassificationValidationError(
            "missing required field(s) in model response: " + ", ".join(missing)
        )


def classify_feedback(
    feedback_id: int,
    product_id: int,
    feedback_text: str,
    vibe: ProductVibe,
    provider: LLMProvider,
    product_context: Optional[ProductContext] = None,
    *,
    temperature: Optional[float] = None,
    timeout_seconds: Optional[float] = None,
    max_length: Optional[int] = None,
) -> ClassificationResult:
    """
    Classify a single feedback record end to end.

    The feedback is preprocessed deterministically; unusable feedback raises
    UnusableFeedbackError before any inference. The prompt is built from the
    supplied Product Vibe (custom taxonomies fully supported) and submitted
    through the configured provider. The raw response is parsed strictly and
    validated into a ClassificationCreate; categories are checked against the
    vibe taxonomy of the prompt that was sent.

    Application-controlled metadata is never taken from the model:
    feedback_id/product_id come from the arguments, model_name from the
    provider identity, prompt_version from the prompt builder, and
    classification_status is set to "active". needs_review is strengthened
    deterministically when confidence falls below the vibe's
    confidence_review_threshold (False -> True only, never the reverse).

    Raises:
        TypeError: If feedback_id or product_id is not an integer.
        UnusableFeedbackError: Empty/over-length feedback or delimiter collision.
        LLMProviderError: Provider failures (propagated unchanged, no retry).
        InvalidResponseError: The response is not a clean JSON object.
        ClassificationValidationError: Schema violations (missing/unexpected
            fields, invalid types or enum values, application-metadata overrides).
        TaxonomyValidationError: A category outside the active vibe taxonomy.
        ValueError: Configuration errors such as an empty vibe taxonomy.
    """
    for name, value in (("feedback_id", feedback_id), ("product_id", product_id)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer, got {type(value).__name__}")

    prepared = prepare_feedback(feedback_text, max_length=max_length)
    if not prepared.is_usable:
        raise UnusableFeedbackError(prepared.reason)

    try:
        prompt = build_classification_prompt(prepared, vibe, product_context)
    except ValueError as exc:
        if FEEDBACK_CLOSE in prepared.prepared_text:
            raise UnusableFeedbackError(str(exc)) from exc
        raise  # configuration error (e.g. empty taxonomy) — not an input problem

    request_temperature = vibe.classification.temperature if temperature is None else temperature
    response = provider.generate(
        prompt.user_prompt,
        system_prompt=prompt.system_prompt,
        temperature=request_temperature,
        timeout_seconds=timeout_seconds,
    )

    data = parse_model_json(response.text)
    _reject_application_controlled_fields(data)
    _reject_unexpected_fields(data)
    _reject_missing_fields(data)

    record = dict(data)
    record["feedback_id"] = feedback_id
    record["product_id"] = product_id
    record["model_name"] = provider.model_name
    # Providers expose no model revision; model_version stays unset rather
    # than invented.
    record["prompt_version"] = prompt.prompt_version
    record["classification_status"] = "active"

    try:
        classification = validate_classification_dict(
            record, valid_categories=prompt.valid_categories
        )
    except ValidationError as exc:
        errors = exc.errors()
        if any(
            error.get("loc") and error["loc"][0] in _TAXONOMY_FIELD_NAMES
            for error in errors
        ):
            first = errors[0]
            raise TaxonomyValidationError(
                f"model named an invalid category at "
                f"{list(first['loc'])}: {first['msg']}"
            ) from exc
        first = errors[0]
        raise ClassificationValidationError(
            f"classification failed schema validation at "
            f"{list(first['loc'])}: {first['msg']}"
        ) from exc

    threshold = vibe.confidence_review_threshold
    if (
        classification.confidence is not None
        and classification.confidence < threshold
        and not classification.needs_review
    ):
        classification.needs_review = True

    return ClassificationResult(
        classification=classification,
        feedback_id=feedback_id,
        product_id=product_id,
        provider_name=response.provider,
        model_name=response.model,
        prompt_version=prompt.prompt_version,
        duration_seconds=response.duration_seconds,
        metadata=dict(response.metadata),
    )
