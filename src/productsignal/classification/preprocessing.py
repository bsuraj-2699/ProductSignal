"""
Deterministic feedback preprocessing for AI classification.

Prepares raw feedback text for inference without rewriting it: whitespace is
normalized, everything else (casing, punctuation, numbers, product names,
technical identifiers, error messages) is preserved verbatim. No summarizing,
paraphrasing, translating, or truncating ever happens here.

The result carries both the untouched original and the prepared text, plus an
explicit usability verdict. Feedback that is empty or exceeds a configured
length limit is reported as not usable — the classification pipeline is
responsible for deterministic fallback handling of unusable feedback.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PreparedFeedback:
    """Result of deterministic preprocessing; original text is never mutated."""

    original_text: str
    prepared_text: str
    is_usable: bool
    reason: Optional[str] = None  # populated whenever is_usable is False


def prepare_feedback(text: str, max_length: Optional[int] = None) -> PreparedFeedback:
    """
    Normalize feedback text deterministically for classification.

    Normalization: every whitespace run (spaces, tabs, newlines) collapses to
    a single space and leading/trailing whitespace is removed. Nothing else is
    altered. The exact-substring evidence rule operates on the ORIGINAL
    feedback text, which is preserved unchanged in PreparedFeedback.

    Length handling is explicit, never silent: when max_length is provided and
    the normalized text exceeds it, the result is marked not usable with a
    reason — the text is NOT truncated.

    Args:
        text: Original feedback text.
        max_length: Optional maximum prepared length in characters. None
            applies no limit.

    Returns:
        PreparedFeedback with is_usable indicating readiness for classification.

    Raises:
        TypeError: If text is not a string.
        ValueError: If max_length is not positive.
    """
    if not isinstance(text, str):
        raise TypeError("feedback text must be a string")
    if max_length is not None and max_length <= 0:
        raise ValueError("max_length must be positive when provided")

    normalized = " ".join(text.split())

    if not normalized:
        return PreparedFeedback(
            original_text=text,
            prepared_text="",
            is_usable=False,
            reason="feedback text is empty",
        )

    if max_length is not None and len(normalized) > max_length:
        return PreparedFeedback(
            original_text=text,
            prepared_text=normalized,
            is_usable=False,
            reason=(
                f"feedback exceeds the configured maximum length "
                f"({len(normalized)} > {max_length} characters)"
            ),
        )

    return PreparedFeedback(original_text=text, prepared_text=normalized, is_usable=True)
