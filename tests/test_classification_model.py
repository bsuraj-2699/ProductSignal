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