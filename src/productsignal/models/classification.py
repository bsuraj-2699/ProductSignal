"""
Classification data models for ProductSignal.

Defines the structure for AI-generated feedback classifications.
"""

import contextvars
from datetime import datetime
from typing import Optional, Literal, Set, FrozenSet, List, get_args
from pydantic import BaseModel, Field, field_validator, ConfigDict


# Valid enum values
SentimentType = Literal["positive", "negative", "neutral", "mixed"]
SeverityType = Literal["low", "medium", "high", "critical"]
ClassificationStatusType = Literal["active", "superseded"]

# Plain tuples for repository-level validation that must work without the
# taxonomy context (e.g. values smuggled in via model_copy(update=...))
SENTIMENT_VALUES: tuple = get_args(SentimentType)
SEVERITY_VALUES: tuple = get_args(SeverityType)
EVIDENCE_SUPPORTS_VALUES: tuple = ("category", "severity", "sentiment", "product_area")

# Classification lifecycle statuses (enforced in models and repository, so the
# rule holds on migrated databases that lack the schema CHECK constraint)
VALID_CLASSIFICATION_STATUSES = ("active", "superseded")

# Classification attempt error types (matches classification_attempts CHECK constraint)
VALID_ATTEMPT_ERROR_TYPES = ("invalid_json", "validation_error", "provider_error", "timeout")

# Database limit for stored raw model responses (classification_attempts.raw_response CHECK)
MAX_RAW_RESPONSE_LENGTH = 8000


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


class EvidenceQuote(BaseModel):
    """
    A verbatim quote from the original feedback text supporting the classification.

    The exact-substring check against feedback.feedback_text is enforced by the
    classification pipeline (later step); the model never alters the quote, so
    what is stored is exactly what was matched.
    """

    model_config = ConfigDict(validate_assignment=True)

    quote: str = Field(..., description="Verbatim quote from the original feedback text")
    supports: Literal["category", "severity", "sentiment", "product_area"] = Field(
        ..., description="Which classification aspect this quote supports"
    )

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, v: str) -> str:
        """Reject empty quotes. The value is never stripped or normalized."""
        if not v or not v.strip():
            raise ValueError("Evidence quote cannot be empty")
        return v


class ClassificationBase(BaseModel):
    """Base classification fields shared by create and record models."""

    # Assignment validation closes the mutation loophole: invalid values
    # assigned after construction are rejected using the same validators
    # (including the taxonomy contextvar) as at construction time.
    # ClassificationCreate and Classification inherit this config.
    model_config = ConfigDict(validate_assignment=True)

    primary_category: str = Field(..., description="Primary problem category")
    secondary_category: Optional[str] = Field(default=None, description="Secondary problem category")
    inferred_product_area: Optional[str] = Field(default=None, description="AI-inferred product area")
    sentiment: SentimentType = Field(..., description="Customer tone (independent of severity)")
    severity: SeverityType = Field(..., description="Issue impact (independent of sentiment)")
    customer_intent: Optional[str] = Field(default=None, description="Customer intent")
    summary: str = Field(..., description="Concise problem statement derived from the feedback")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Classification confidence (0-1); NULL when no model assessment occurred",
    )
    needs_review: bool = Field(default=False, description="Flag for human review")

    # Phase 3.1 extensions
    evidence_quotes: Optional[List[EvidenceQuote]] = Field(
        default=None,
        description="Verbatim quotes from the original feedback supporting the classification",
    )
    classification_reasoning: Optional[str] = Field(
        default=None,
        description="Model explanation; audit trail only, never treated as evidence",
    )
    mentioned_feature: Optional[str] = Field(
        default=None, description="Explicit product feature/component named in the feedback"
    )
    is_actionable: Optional[bool] = Field(
        default=None, description="Whether the feedback contains an actionable problem"
    )
    classification_status: ClassificationStatusType = Field(
        default="active",
        description="Lifecycle status: active (current) or superseded (history)",
    )

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
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        """Validate confidence is between 0 and 1, or None (not assessed)."""
        if v is None:
            return v
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
    model_name: Optional[str] = Field(
        default=None, description="Model that produced this classification (e.g. 'qwen2.5:7b', 'human', 'deterministic')"
    )
    prompt_version: Optional[str] = Field(default=None, description="Prompt template version used")
    error_note: Optional[str] = Field(
        default=None, description="Operational note set when a reclassification attempt failed"
    )
    feedback_id: int = Field(..., description="Associated feedback ID")
    product_id: int = Field(..., description="Associated product ID")


class Classification(ClassificationBase):
    """Complete classification record with database fields."""

    classification_id: int = Field(..., description="Internal database ID")
    feedback_id: int = Field(..., description="Associated feedback ID")
    product_id: int = Field(..., description="Associated product ID")
    model_version: Optional[str] = Field(default=None, description="LLM model version used")
    model_name: Optional[str] = Field(
        default=None, description="Model that produced this classification (e.g. 'qwen2.5:7b', 'human', 'deterministic')"
    )
    prompt_version: Optional[str] = Field(default=None, description="Prompt template version used")
    error_note: Optional[str] = Field(
        default=None, description="Operational note set when a reclassification attempt failed"
    )
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
            evidence_quotes=create.evidence_quotes,
            classification_reasoning=create.classification_reasoning,
            mentioned_feature=create.mentioned_feature,
            is_actionable=create.is_actionable,
            classification_status=create.classification_status,
            model_version=create.model_version,
            model_name=create.model_name,
            prompt_version=create.prompt_version,
            error_note=create.error_note,
        )


class ClassificationAttempt(BaseModel):
    """Record of a failed classification attempt (from classification_attempts)."""

    model_config = ConfigDict(validate_assignment=True)

    attempt_id: int = Field(..., description="Internal database ID")
    feedback_id: int = Field(..., description="Feedback the attempt was made for")
    product_id: int = Field(..., description="Associated product ID")
    model_name: Optional[str] = Field(default=None, description="Model used for the attempt")
    prompt_version: Optional[str] = Field(default=None, description="Prompt version used")
    attempt_number: int = Field(..., ge=1, description="1-based attempt counter for the feedback record")
    error_type: Literal["invalid_json", "validation_error", "provider_error", "timeout"] = Field(
        ..., description="Failure class"
    )
    error_detail: Optional[str] = Field(default=None, description="Failure details for forensics")
    raw_response: Optional[str] = Field(
        default=None, description="Raw model output, truncated to 8,000 characters"
    )
    attempted_at: datetime = Field(default_factory=datetime.now, description="Attempt timestamp")


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