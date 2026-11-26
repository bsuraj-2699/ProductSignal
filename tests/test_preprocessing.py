"""
Tests for deterministic feedback preprocessing (Phase 3.1.4a).
"""

import pytest

from productsignal.classification.preprocessing import PreparedFeedback, prepare_feedback


class TestPreprocessing:
    def test_whitespace_runs_collapse_to_single_spaces(self):
        raw = "Dashboard   slow.\n\nLoads\t\tforever\n  when  busy."
        result = prepare_feedback(raw)
        assert result.is_usable is True
        assert result.prepared_text == "Dashboard slow. Loads forever when busy."

    def test_leading_and_trailing_whitespace_removed(self):
        result = prepare_feedback("   \n  app keeps crashing  \t ")
        assert result.prepared_text == "app keeps crashing"

    def test_punctuation_and_casing_preserved(self):
        raw = "The Dashboard CRASHED!! (v2.3.1) — see error: 'E-404: timeout??'"
        result = prepare_feedback(raw)
        assert result.prepared_text == raw.strip()

    def test_numbers_and_technical_identifiers_preserved(self):
        raw = "GET /api/v2/reports?limit=50 returns HTTP 500 (ERR_CONN_RESET_42) since 2026-01-15"
        result = prepare_feedback(raw)
        assert result.prepared_text == raw

    def test_original_text_preserved_and_input_not_mutated(self):
        raw = "line one\n   line\ttwo   "
        result = prepare_feedback(raw)
        assert result.original_text == raw      # exact original kept on the result
        assert raw == "line one\n   line\ttwo   "  # source untouched

    def test_empty_feedback_not_usable(self):
        result = prepare_feedback("")
        assert result.is_usable is False
        assert result.reason == "feedback text is empty"
        assert result.prepared_text == ""

    def test_whitespace_only_feedback_not_usable(self):
        result = prepare_feedback("   \n\t  ")
        assert result.is_usable is False
        assert result.reason is not None

    def test_no_limit_long_feedback_usable_and_untruncated(self):
        raw = "word " * 5000  # 25,000 characters
        result = prepare_feedback(raw)
        assert result.is_usable is True
        assert result.reason is None
        assert len(result.prepared_text) == len(" ".join(raw.split()))

    def test_length_limit_marks_unusable_without_truncation(self):
        raw = "ab " * 60  # normalized length 179
        result = prepare_feedback(raw, max_length=100)
        assert result.is_usable is False
        assert "maximum length" in result.reason
        assert "179 > 100" in result.reason
        # Not truncated: full normalized text is still present
        assert result.prepared_text == " ".join(raw.split())
        assert len(result.prepared_text) > 100

    def test_length_limit_boundary_exact_length_usable(self):
        raw = "x" * 100
        result = prepare_feedback(raw, max_length=100)
        assert result.is_usable is True

    def test_invalid_max_length_rejected(self):
        with pytest.raises(ValueError, match="max_length must be positive"):
            prepare_feedback("text", max_length=0)
        with pytest.raises(ValueError, match="max_length must be positive"):
            prepare_feedback("text", max_length=-5)

    def test_non_string_input_rejected(self):
        with pytest.raises(TypeError, match="must be a string"):
            prepare_feedback(None)
        with pytest.raises(TypeError, match="must be a string"):
            prepare_feedback(123)

    def test_deterministic_repeatability(self):
        raw = "Flaky\t sync\n\n fails  sometimes!! (build #417)"
        first = prepare_feedback(raw, max_length=1000)
        second = prepare_feedback(raw, max_length=1000)
        assert first == second  # frozen dataclass equality, fully deterministic

    def test_result_is_frozen(self):
        result = prepare_feedback("text")
        with pytest.raises(Exception):
            result.prepared_text = "mutated"
