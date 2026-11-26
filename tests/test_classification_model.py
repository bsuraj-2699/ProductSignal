"""
Tests for Classification data models.
"""

import pytest
from pydantic import ValidationError

from productsignal.models.classification import (
    ClassificationCreate,
    Classification,
    validate_classification_dict,
    DEFAULT_PRIMARY_CATEGORIES,
    get_valid_categories_from_vibe,
)


class TestClassificationCreate:
    """Tests for ClassificationCreate model validation."""

    def test_valid_classification_create(self):
        """Test creating valid classification."""
        classification = ClassificationCreate(
            feedback_id=1,
            product_id=1,
            primary_category="reliability_downtime",
            secondary_category="performance_speed",
            inferred_product_area="dashboard",
            sentiment="negative",
            severity="high",
            customer_intent="report_issue",
            summary="Dashboard crashes frequently",
            confidence=0.9,
            needs_review=False,
            model_version="qwen2.5:7b",
        )
        assert classification.primary_category == "reliability_downtime"
        assert classification.confidence == 0.9

    def test_minimal_classification_create(self):
        """Test creating classification with required fields only."""
        classification = ClassificationCreate(
            feedback_id=1,
            product_id=1,
            primary_category="feature_request",
            sentiment="neutral",
            severity="low",
            summary="Customer wants dark mode",
            confidence=0.8,
        )
        assert classification.primary_category == "feature_request"
        assert classification.secondary_category is None
        assert classification.needs_review is False  # Default

    def test_all_valid_primary_categories(self):
        """Test that all default primary categories are accepted."""
        for category in DEFAULT_PRIMARY_CATEGORIES:
            classification = ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category=category,
                sentiment="negative",
                severity="medium",
                summary=f"Test {category}",
                confidence=0.7,
            )
            assert classification.primary_category == category

    def test_invalid_primary_category_rejected(self):
        """Test that invalid primary category is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="invalid_category",
                sentiment="negative",
                severity="medium",
                summary="Test",
                confidence=0.7,
            )
        assert "Invalid primary_category" in str(exc_info.value)

    def test_invalid_secondary_category_rejected(self):
        """Test that invalid secondary category is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="reliability_downtime",
                secondary_category="invalid_secondary",
                sentiment="negative",
                severity="medium",
                summary="Test",
                confidence=0.7,
            )
        assert "Invalid secondary_category" in str(exc_info.value)

    def test_valid_sentiments(self):
        """Test all valid sentiment values."""
        for sentiment in ["positive", "negative", "neutral", "mixed"]:
            classification = ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="feature_request",
                sentiment=sentiment,
                severity="low",
                summary="Test",
                confidence=0.7,
            )
            assert classification.sentiment == sentiment

    def test_invalid_sentiment_rejected(self):
        """Test that invalid sentiment is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="feature_request",
                sentiment="invalid_sentiment",
                severity="low",
                summary="Test",
                confidence=0.7,
            )
        assert "sentiment" in str(exc_info.value).lower()

    def test_valid_severities(self):
        """Test all valid severity values."""
        for severity in ["low", "medium", "high", "critical"]:
            classification = ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="feature_request",
                sentiment="negative",
                severity=severity,
                summary="Test",
                confidence=0.7,
            )
            assert classification.severity == severity

    def test_invalid_severity_rejected(self):
        """Test that invalid severity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="feature_request",
                sentiment="negative",
                severity="invalid_severity",
                summary="Test",
                confidence=0.7,
            )
        assert "severity" in str(exc_info.value).lower()

    def test_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        # Valid boundaries
        ClassificationCreate(
            feedback_id=1, product_id=1, primary_category="feature_request",
            sentiment="neutral", severity="low", summary="Test", confidence=0.0
        )
        ClassificationCreate(
            feedback_id=1, product_id=1, primary_category="feature_request",
            sentiment="neutral", severity="low", summary="Test", confidence=1.0
        )

        # Invalid - Pydantic v2 uses "greater_than_equal" and "less_than_equal" messages
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1, product_id=1, primary_category="feature_request",
                sentiment="neutral", severity="low", summary="Test", confidence=-0.1
            )
        assert "greater_than_equal" in str(exc_info.value) or "Confidence must be between" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1, product_id=1, primary_category="feature_request",
                sentiment="neutral", severity="low", summary="Test", confidence=1.1
            )
        assert "less_than_equal" in str(exc_info.value) or "Confidence must be between" in str(exc_info.value)

    def test_summary_validation(self):
        """Test summary cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(
                feedback_id=1, product_id=1, primary_category="feature_request",
                sentiment="neutral", severity="low", summary="", confidence=0.7
            )
        assert "Summary cannot be empty" in str(exc_info.value)

    def test_summary_strips_whitespace(self):
        """Test summary is stripped."""
        classification = ClassificationCreate(
            feedback_id=1, product_id=1, primary_category="feature_request",
            sentiment="neutral", severity="low", summary="  Test summary  ", confidence=0.7
        )
        assert classification.summary == "Test summary"


class TestClassificationRecord:
    """Tests for Classification record model."""

    def test_classification_record_creation(self):
        """Test creating a complete classification record."""
        from datetime import datetime
        record = Classification(
            classification_id=1,
            feedback_id=1,
            product_id=1,
            primary_category="reliability_downtime",
            sentiment="negative",
            severity="high",
            summary="System crashes",
            confidence=0.95,
            model_version="qwen2.5:7b",
            classified_at=datetime(2024, 1, 15, 10, 30),
        )
        assert record.classification_id == 1
        assert record.confidence == 0.95

    def test_from_create_method(self):
        """Test creating Classification from ClassificationCreate."""
        create = ClassificationCreate(
            feedback_id=1,
            product_id=1,
            primary_category="feature_request",
            sentiment="positive",
            severity="low",
            summary="Customer loves the new feature",
            confidence=0.85,
            model_version="test-model",
        )
        record = Classification.from_create(create)
        assert record.feedback_id == 1
        assert record.product_id == 1
        assert record.primary_category == "feature_request"
        assert record.model_version == "test-model"
        assert record.classification_id == 0  # Not set by DB yet


class TestValidateClassificationDict:
    """Tests for validate_classification_dict helper."""

    def test_valid_dict(self):
        """Test validating a valid dictionary."""
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "performance_speed",
            "sentiment": "negative",
            "severity": "medium",
            "summary": "Slow performance",
            "confidence": 0.8,
        }
        result = validate_classification_dict(data)
        assert isinstance(result, ClassificationCreate)
        assert result.primary_category == "performance_speed"

    def test_invalid_dict_raises(self):
        """Test that invalid dict raises ValidationError."""
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "invalid_category",
            "sentiment": "negative",
            "severity": "medium",
            "summary": "Test",
            "confidence": 0.8,
        }
        with pytest.raises(ValidationError):
            validate_classification_dict(data)


class TestConfigurableTaxonomy:
    """Tests for configurable taxonomy validation (F6)."""

    def test_validate_with_custom_categories(self):
        """Test validation with explicitly supplied taxonomy."""
        custom_categories = {"custom_cat_1", "custom_cat_2", "custom_cat_3"}
        
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "custom_cat_1",
            "sentiment": "negative",
            "severity": "medium",
            "summary": "Custom category test",
            "confidence": 0.8,
        }
        result = validate_classification_dict(data, valid_categories=custom_categories)
        assert result.primary_category == "custom_cat_1"

    def test_validate_rejects_invalid_custom_category(self):
        """Test that invalid category is rejected with custom taxonomy."""
        custom_categories = {"custom_cat_1", "custom_cat_2"}
        
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "invalid_cat",
            "sentiment": "negative",
            "severity": "medium",
            "summary": "Test",
            "confidence": 0.8,
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_classification_dict(data, valid_categories=custom_categories)
        assert "invalid_cat" in str(exc_info.value)

    def test_validate_with_active_vibe(self, sample_saas_vibe):
        """Test validation uses active vibe taxonomy when available."""
        from productsignal.config import set_active_vibe, clear_vibe_cache
        
        clear_vibe_cache()
        set_active_vibe(sample_saas_vibe)
        
        # Valid SaaS category should work
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "reliability_downtime",
            "sentiment": "negative",
            "severity": "high",
            "summary": "System crash",
            "confidence": 0.9,
        }
        result = validate_classification_dict(data)
        assert result.primary_category == "reliability_downtime"
        
        # Invalid for SaaS should fail
        data_invalid = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "mobile_app_crash",  # Not in SaaS taxonomy
            "sentiment": "negative",
            "severity": "high",
            "summary": "App crash",
            "confidence": 0.9,
        }
        with pytest.raises(ValidationError):
            validate_classification_dict(data_invalid)

    def test_get_valid_categories_from_vibe(self, sample_saas_vibe):
        """Test extracting categories from vibe."""
        from productsignal.models.classification import get_valid_categories_from_vibe
        
        categories = get_valid_categories_from_vibe(sample_saas_vibe)
        assert isinstance(categories, frozenset)
        assert "reliability_downtime" in categories
        assert "feature_request" in categories
        assert len(categories) == 12

class TestPhase31ClassificationFields:
    """Tests for the Phase 3.1 classification model extensions."""

    def _base_kwargs(self, **overrides):
        kwargs = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "reliability_downtime",
            "sentiment": "negative",
            "severity": "high",
            "summary": "Dashboard crashes on load",
            "confidence": 0.9,
        }
        kwargs.update(overrides)
        return kwargs

    def test_new_fields_accepted(self):
        from productsignal.models.classification import EvidenceQuote

        classification = ClassificationCreate(
            **self._base_kwargs(
                evidence_quotes=[
                    EvidenceQuote(quote="Dashboard crashes on load", supports="category"),
                    EvidenceQuote(quote="crashes", supports="severity"),
                ],
                classification_reasoning="Crash wording indicates reliability issue",
                mentioned_feature="dashboard",
                is_actionable=True,
                model_name="qwen2.5:7b",
                prompt_version="cls-v1",
            )
        )
        assert len(classification.evidence_quotes) == 2
        assert classification.evidence_quotes[0].quote == "Dashboard crashes on load"
        assert classification.evidence_quotes[0].supports == "category"
        assert classification.classification_reasoning == "Crash wording indicates reliability issue"
        assert classification.mentioned_feature == "dashboard"
        assert classification.is_actionable is True
        assert classification.model_name == "qwen2.5:7b"
        assert classification.prompt_version == "cls-v1"

    def test_evidence_quote_rejects_empty(self):
        from productsignal.models.classification import EvidenceQuote

        with pytest.raises(ValidationError):
            EvidenceQuote(quote="", supports="category")
        with pytest.raises(ValidationError):
            EvidenceQuote(quote="   ", supports="severity")

    def test_evidence_quote_rejects_invalid_supports(self):
        from productsignal.models.classification import EvidenceQuote

        with pytest.raises(ValidationError):
            EvidenceQuote(quote="text", supports="fabricated_aspect")

    def test_evidence_quote_value_not_modified(self):
        """The quote is stored exactly as provided — never stripped or normalized."""
        from productsignal.models.classification import EvidenceQuote

        quote = EvidenceQuote(quote="  Dashboard crashes  ", supports="category")
        assert quote.quote == "  Dashboard crashes  "

    def test_classification_status_defaults_to_active(self):
        classification = ClassificationCreate(**self._base_kwargs())
        assert classification.classification_status == "active"

    def test_classification_status_superseded_accepted(self):
        classification = ClassificationCreate(
            **self._base_kwargs(classification_status="superseded")
        )
        assert classification.classification_status == "superseded"

    def test_invalid_classification_status_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ClassificationCreate(**self._base_kwargs(classification_status="pending"))
        # Pydantic's Literal rejects invalid statuses before any field validator
        assert "Input should be 'active' or 'superseded'" in str(exc_info.value)

    def test_null_confidence_allowed(self):
        """Deterministic fallback rows carry NULL confidence (no false certainty)."""
        classification = ClassificationCreate(
            **self._base_kwargs(confidence=None, is_actionable=False, needs_review=True)
        )
        assert classification.confidence is None

    def test_confidence_out_of_range_still_rejected(self):
        with pytest.raises(ValidationError):
            ClassificationCreate(**self._base_kwargs(confidence=1.5))
        with pytest.raises(ValidationError):
            ClassificationCreate(**self._base_kwargs(confidence=-0.1))

    def test_from_create_preserves_null_confidence(self):
        create = ClassificationCreate(**self._base_kwargs(confidence=None))
        record = Classification.from_create(create)
        assert record.confidence is None
        assert record.classification_status == "active"

    def test_sentiment_and_severity_independent(self):
        """Positive tone with critical impact is legitimate — no cross-rejection."""
        classification = ClassificationCreate(
            **self._base_kwargs(sentiment="positive", severity="critical")
        )
        assert classification.sentiment == "positive"
        assert classification.severity == "critical"

        classification_mixed = ClassificationCreate(
            **self._base_kwargs(sentiment="mixed", severity="critical")
        )
        assert classification_mixed.sentiment == "mixed"

    def test_validate_classification_dict_with_phase31_fields(self):
        from productsignal.models.classification import EvidenceQuote

        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "reliability_downtime",
            "sentiment": "negative",
            "severity": "critical",
            "summary": "System down",
            "confidence": 0.85,
            "evidence_quotes": [
                {"quote": "system down", "supports": "severity"},
            ],
            "classification_reasoning": "Outage language",
            "is_actionable": True,
            "classification_status": "active",
            "model_name": "qwen2.5:7b",
        }
        result = validate_classification_dict(data)
        assert result.evidence_quotes[0].quote == "system down"
        assert result.model_name == "qwen2.5:7b"

    def test_null_confidence_via_validate_classification_dict(self):
        data = {
            "feedback_id": 1,
            "product_id": 1,
            "primary_category": "other_unclear",
            "sentiment": "neutral",
            "severity": "low",
            "summary": "Unclassifiable — insufficient content (deterministic fallback)",
            "confidence": None,
            "needs_review": True,
            "is_actionable": False,
            "model_name": "deterministic",
        }
        result = validate_classification_dict(data)
        assert result.confidence is None
        assert result.needs_review is True

    def test_invalid_error_type_constant_matches_schema(self):
        from productsignal.models.classification import (
            VALID_ATTEMPT_ERROR_TYPES,
            VALID_CLASSIFICATION_STATUSES,
            MAX_RAW_RESPONSE_LENGTH,
        )
        assert VALID_ATTEMPT_ERROR_TYPES == (
            "invalid_json", "validation_error", "provider_error", "timeout"
        )
        assert VALID_CLASSIFICATION_STATUSES == ("active", "superseded")
        assert MAX_RAW_RESPONSE_LENGTH == 8000


class TestAssignmentValidation:
    """Assignment-time validation (validate_assignment=True) closes the
    mutation loophole: invalid values set after construction are rejected (Issue 2)."""

    def _valid_create(self):
        return ClassificationCreate(
            feedback_id=1,
            product_id=1,
            primary_category="reliability_downtime",
            sentiment="negative",
            severity="high",
            summary="Dashboard crashes on load",
            confidence=0.9,
        )

    def test_invalid_sentiment_assignment_rejected(self):
        classification = self._valid_create()
        with pytest.raises(ValidationError):
            classification.sentiment = "hostile"
        assert classification.sentiment == "negative"  # unchanged

    def test_invalid_severity_assignment_rejected(self):
        classification = self._valid_create()
        with pytest.raises(ValidationError):
            classification.severity = "cosmic"
        assert classification.severity == "high"

    def test_invalid_primary_category_assignment_rejected(self):
        classification = self._valid_create()
        with pytest.raises(ValidationError):
            classification.primary_category = "not_a_real_category"
        assert classification.primary_category == "reliability_downtime"

    def test_invalid_classification_status_assignment_rejected(self):
        classification = self._valid_create()
        with pytest.raises(ValidationError):
            classification.classification_status = "pending"
        assert classification.classification_status == "active"

    def test_invalid_confidence_assignment_rejected(self):
        classification = self._valid_create()
        with pytest.raises(ValidationError):
            classification.confidence = 1.7
        assert classification.confidence == 0.9

    def test_valid_assignments_accepted(self):
        classification = self._valid_create()
        classification.sentiment = "positive"
        classification.severity = "critical"
        classification.primary_category = "performance_speed"
        classification.classification_status = "superseded"
        classification.confidence = None
        classification.needs_review = True

        assert classification.sentiment == "positive"
        assert classification.severity == "critical"
        assert classification.primary_category == "performance_speed"
        assert classification.classification_status == "superseded"
        assert classification.confidence is None
        assert classification.needs_review is True

    def test_assignment_validates_on_record_model(self):
        record = Classification.from_create(self._valid_create())
        with pytest.raises(ValidationError):
            record.classification_status = "archived"
        record.classification_status = "superseded"  # valid still works
        assert record.classification_status == "superseded"

    def test_evidence_quote_invalid_assignment_rejected(self):
        from productsignal.models.classification import EvidenceQuote

        quote = EvidenceQuote(quote="crashes", supports="category")
        with pytest.raises(ValidationError):
            quote.quote = ""
        with pytest.raises(ValidationError):
            quote.quote = "   "
        with pytest.raises(ValidationError):
            quote.supports = "fabricated_aspect"
        assert quote.quote == "crashes"
        assert quote.supports == "category"

    def test_evidence_quote_valid_assignment_accepted(self):
        from productsignal.models.classification import EvidenceQuote

        quote = EvidenceQuote(quote="crashes", supports="category")
        quote.quote = "crashes on load"
        quote.supports = "severity"
        assert quote.quote == "crashes on load"
        assert quote.supports == "severity"

    def test_classification_attempt_invalid_assignment_rejected(self):
        from productsignal.models.classification import ClassificationAttempt

        attempt = ClassificationAttempt(
            attempt_id=1, feedback_id=1, product_id=1,
            attempt_number=1, error_type="timeout",
        )
        with pytest.raises(ValidationError):
            attempt.attempt_number = 0
        with pytest.raises(ValidationError):
            attempt.error_type = "weird_error"
        assert attempt.attempt_number == 1
        assert attempt.error_type == "timeout"

    def test_assignment_respects_custom_vibe_taxonomy(self):
        """Assignment validation uses the same taxonomy context as construction,
        so custom Product Vibe taxonomies keep working."""
        custom_categories = frozenset({"legacy_export", "custom_category"})
        from productsignal.models.classification import _valid_categories_ctx
        token = _valid_categories_ctx.set(custom_categories)
        try:
            classification = ClassificationCreate(
                feedback_id=1,
                product_id=1,
                primary_category="custom_category",
                sentiment="negative",
                severity="high",
                summary="Dashboard crashes on load",
            )
            # A default-taxonomy category is invalid under the custom vibe
            with pytest.raises(ValidationError):
                classification.primary_category = "reliability_downtime"
            # A custom-taxonomy category is accepted
            classification.primary_category = "legacy_export"
            assert classification.primary_category == "legacy_export"
        finally:
            _valid_categories_ctx.reset(token)

    def test_evidence_supports_values_match_literal(self):
        import typing
        from productsignal.models.classification import EvidenceQuote, EVIDENCE_SUPPORTS_VALUES

        literal_args = typing.get_args(EvidenceQuote.model_fields["supports"].annotation)
        assert EVIDENCE_SUPPORTS_VALUES == literal_args

    def test_sentiment_severity_values_match_literals(self):
        import typing
        from productsignal.models.classification import (
            ClassificationBase, SENTIMENT_VALUES, SEVERITY_VALUES,
        )

        assert SENTIMENT_VALUES == typing.get_args(ClassificationBase.model_fields["sentiment"].annotation)
        assert SEVERITY_VALUES == typing.get_args(ClassificationBase.model_fields["severity"].annotation)
