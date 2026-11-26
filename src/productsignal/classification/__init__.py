"""Classification persistence and inference-preparation layer for ProductSignal."""

from .repository import ClassificationRepository, get_classification_repository
from .preprocessing import PreparedFeedback, prepare_feedback
from .prompting import (
    PROMPT_VERSION,
    ClassificationPrompt,
    build_classification_prompt,
)
from .service import (
    ClassificationError,
    ClassificationResult,
    ClassificationValidationError,
    InvalidResponseError,
    TaxonomyValidationError,
    UnusableFeedbackError,
    classify_feedback,
    parse_model_json,
)

__all__ = [
    "ClassificationRepository",
    "get_classification_repository",
    "PreparedFeedback",
    "prepare_feedback",
    "PROMPT_VERSION",
    "ClassificationPrompt",
    "build_classification_prompt",
    "ClassificationError",
    "ClassificationResult",
    "ClassificationValidationError",
    "InvalidResponseError",
    "TaxonomyValidationError",
    "UnusableFeedbackError",
    "classify_feedback",
    "parse_model_json",
]
