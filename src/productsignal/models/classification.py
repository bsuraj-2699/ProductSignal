"""
Classification data models for ProductSignal.

Defines the structure for AI-generated feedback classifications.
"""

import contextvars
from datetime import datetime
from typing import Optional, Literal, Set, FrozenSet
from pydantic import BaseModel, Field, field_validator


# Valid enum values
SentimentType = Literal["positive", "negative", "neutral", "mixed"]
SeverityType = Literal["low", "medium", "high", "critical"]


# Default SaaS Classification Taxonomy (fallback when no vibe is available)
# This is the same as config/vibes/saas.yaml for backwards compatibility
DEFAULT_PRIMARY_CATEGORIES: FrozenSet[str] = frozenset([
    "reliability_downtime",
    "performance_speed",
    "workflow_efficiency",
    "feature_usability",
    "user_onboarding",
    "integration_issues",
    "reporting_analytics",
    "data_accuracy",
    "feature_request",
    "pricing_value",
    "customer_support",
    "other_unclear",
])


# Context variable for configurable taxonomy (thread-safe)
_valid_categories_ctx: contextvars.ContextVar[Optional[FrozenSet[str]]] = contextvars.ContextVar(
    "_valid_categories_ctx", default=None
)


class ClassificationBase(BaseModel):
    """Base classification fields shared by create and record models."""

    primary_category: str = Field(..., description="Primary problem category")
    secondary_category: Optional[str] = Field(default=None, description="Secondary problem category")
    inferred_product_area: Optional[str] = Field(default=None, description="AI-inferred product area")
    sentiment: SentimentType = Field(..., description="Customer sentiment")
    severity: SeverityType = Field(..., description="Problem severity")
    customer_intent: Optional[str] = Field(default=None, description="Customer intent")
    summary: str = Field(..., description="Short summary of the feedback")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence (0-1)")
    needs_review: bool = Field(default=False, description="Flag for human review")

    @field_validator("primary_category")
    @classmethod
    def validate_primary_category(cls, v: str, info) -> str:
        """Validate primary category against configured taxonomy."""
        # Get valid categories from context or use default
        valid_categories = _valid_categories_ctx.get() or DEFAULT_PRIMARY_CATEGORIES
        if v not in valid_categories:
            raise ValueError(f"Invalid primary_category: {v}. Must be one of: {sorted(valid_categories)}")
        return v

    @field_validator("secondary_category")
    @classmethod
    def validate_secondary_category(cls, v: Optional[str], info) -> Optional[str]:
        """Validate secondary category if provided."""
        if v is not None:
            valid_categories = _valid_categories_ctx.get() or DEFAULT_PRIMARY_CATEGORIES
            if v not in valid_categories:
                raise ValueError(f"Invalid secondary_category: {v}. Must be one of: {sorted(valid_categories)}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        """Validate summary is not empty."""
        if not v or not v.strip():
            raise ValueError("Summary cannot be empty")
        return v.strip()


class ClassificationCreate(ClassificationBase):
    """Model for creating new classification records."""

    model_version: Optional[str] = Field(default=None, description="LLM model version used")
    feedback_id: int = Field(..., description="Associated feedback ID")
    product_id: int = Field(..., description="Associated product ID")


class Classification(ClassificationBase):
    """Complete classification record with database fields."""

    classification_id: int = Field(..., description="Internal database ID")
    feedback_id: int = Field(..., description="Associated feedback ID")
    product_id: int = Field(..., description="Associated product ID")
    model_version: Optional[str] = Field(default=None, description="LLM model version used")
    classified_at: datetime = Field(default_factory=datetime.now, description="Classification timestamp")

    @classmethod
    def from_create(cls, create: ClassificationCreate) -> "Classification":
        """Create a Classification from ClassificationCreate."""
        return cls(
            classification_id=0,  # Will be set by database
            feedback_id=create.feedback_id,
            product_id=create.product_id,
            primary_category=create.primary_category,
            secondary_category=create.secondary_category,
            inferred_product_area=create.inferred_product_area,
            sentiment=create.sentiment,
            severity=create.severity,
            customer_intent=create.customer_intent,
            summary=create.summary,
            confidence=create.confidence,
            needs_review=create.needs_review,
            model_version=create.model_version,
        )


def get_valid_categories_from_vibe(vibe) -> FrozenSet[str]:
    """
    Extract valid classification categories from a ProductVibe instance.
    
    Args:
        vibe: ProductVibe instance from config
        
    Returns:
        FrozenSet of valid primary category strings
    """
    categories = vibe.classification_taxonomy.get("primary_categories", [])
    return frozenset(categories)


def validate_classification_dict(data: dict, valid_categories: Optional[Set[str]] = None) -> ClassificationCreate:
    """
    Validate a classification dictionary and return a ClassificationCreate model.

    This is used for validating LLM outputs before database insertion.
    
    Args:
        data: Dictionary with classification data
        valid_categories: Optional set of valid categories. If not provided,
            uses DEFAULT_PRIMARY_CATEGORIES or extracts from active vibe.
            
    Returns:
        Validated ClassificationCreate model
    """
    # Determine valid categories
    if valid_categories is None:
        # Try to get from active vibe
        from productsignal.config import get_active_vibe
        active_vibe = get_active_vibe()
        if active_vibe is not None:
            valid_categories = get_valid_categories_from_vibe(active_vibe)
        else:
            valid_categories = DEFAULT_PRIMARY_CATEGORIES
    
    # Set context variable for validation
    token = _valid_categories_ctx.set(frozenset(valid_categories))
    try:
        return ClassificationCreate(**data)
    finally:
        _valid_categories_ctx.reset(token)