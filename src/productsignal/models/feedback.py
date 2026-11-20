"""
Feedback data models for ProductSignal.

Defines the structure for customer feedback records.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import hashlib


def normalize_feedback_text(text: str) -> str:
    """
    Normalize feedback text for content hash calculation.
    
    Normalization principle: " ".join(text.lower().split())
    - Multiple spaces are normalized to single space
    - Leading and trailing whitespace is removed
    - Text is converted to lowercase
    
    Original feedback text remains unchanged in the database.
    """
    return " ".join(text.lower().split())


def compute_content_hash(text: str) -> str:
    """
    Compute SHA256 hash of normalized text for duplicate detection.
    
    Args:
        text: Raw feedback text (will be normalized before hashing)
        
    Returns:
        SHA256 hex digest of normalized text
    """
    normalized = normalize_feedback_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class FeedbackCreate(BaseModel):
    """Model for creating new feedback records from user input."""

    feedback_id: Optional[str] = Field(default=None, description="External feedback identifier")
    feedback_text: str = Field(..., description="Original customer feedback text")
    source: Optional[str] = Field(default=None, description="Feedback source channel")
    created_at: Optional[datetime] = Field(default=None, description="Feedback creation date")
    customer_segment: Optional[str] = Field(default=None, description="Customer segment")
    product_area: Optional[str] = Field(default=None, description="Product area")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="Customer rating (1-5)")
    original_category: Optional[str] = Field(default=None, description="Original category from source")

    @field_validator("feedback_text")
    @classmethod
    def validate_feedback_text(cls, v: str) -> str:
        """Validate and clean feedback text."""
        if not v or not v.strip():
            raise ValueError("Feedback text cannot be empty")
        cleaned = v.strip()
        if len(cleaned) > 10000:
            raise ValueError("Feedback text exceeds maximum length of 10,000 characters")
        return cleaned

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        """Validate rating is between 1 and 5."""
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Rating must be between 1 and 5")
        return v


class FeedbackRecord(BaseModel):
    """Complete feedback record with database fields."""

    feedback_id: int = Field(..., description="Internal database ID")
    product_id: int = Field(..., description="Associated product ID")
    external_id: Optional[str] = Field(default=None, description="External source identifier")
    content_hash: str = Field(..., description="SHA256 hash of normalized feedback text")
    feedback_text: str = Field(..., description="Original customer feedback text (unchanged)")
    source: Optional[str] = Field(default=None, description="Feedback source channel")
    created_at: Optional[datetime] = Field(default=None, description="Feedback creation date")
    customer_segment: Optional[str] = Field(default=None, description="Customer segment")
    product_area: Optional[str] = Field(default=None, description="Product area")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="Customer rating (1-5)")
    original_category: Optional[str] = Field(default=None, description="Original category from source")
    imported_at: datetime = Field(default_factory=datetime.now, description="Import timestamp")

    @field_validator("feedback_text")
    @classmethod
    def validate_feedback_text(cls, v: str) -> str:
        """Validate feedback text is not empty."""
        if not v or not v.strip():
            raise ValueError("Feedback text cannot be empty")
        return v.strip()

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        """Validate rating is between 1 and 5."""
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    @classmethod
    def from_create(cls, create: FeedbackCreate, product_id: int, content_hash: str) -> "FeedbackRecord":
        """Create a FeedbackRecord from FeedbackCreate with computed fields."""
        return cls(
            feedback_id=0,  # Will be set by database
            product_id=product_id,
            external_id=create.feedback_id,
            content_hash=content_hash,
            feedback_text=create.feedback_text,
            source=create.source,
            created_at=create.created_at,
            customer_segment=create.customer_segment,
            product_area=create.product_area,
            rating=create.rating,
            original_category=create.original_category,
        )

    def compute_content_hash(self) -> str:
        """Compute SHA256 hash of feedback text for duplicate detection."""
        return compute_content_hash(self.feedback_text)