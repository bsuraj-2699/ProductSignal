"""
Tests for Feedback data models.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime

from productsignal.models.feedback import FeedbackCreate, FeedbackRecord, compute_content_hash


class TestFeedbackCreate:
    """Tests for FeedbackCreate model validation."""

    def test_valid_feedback_create(self):
        """Test creating valid feedback."""
        feedback = FeedbackCreate(
            feedback_id="EXT-123",
            feedback_text="This is a valid feedback comment.",
            source="support_ticket",
            created_at=datetime(2024, 1, 15, 10, 30),
            customer_segment="enterprise",
            product_area="dashboard",
            rating=4,
            original_category="performance",
        )
        assert feedback.feedback_text == "This is a valid feedback comment."
        assert feedback.rating == 4

    def test_minimal_feedback_create(self):
        """Test creating feedback with only required fields."""
        feedback = FeedbackCreate(feedback_text="Minimal feedback")
        assert feedback.feedback_text == "Minimal feedback"
        assert feedback.feedback_id is None
        assert feedback.source is None
        assert feedback.rating is None

    def test_feedback_text_strips_whitespace(self):
        """Test that feedback text is stripped of surrounding whitespace."""
        feedback = FeedbackCreate(feedback_text="  Trimmed text  ")
        assert feedback.feedback_text == "Trimmed text"

    def test_empty_feedback_rejected(self):
        """Test that empty feedback is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate(feedback_text="")
        assert "Feedback text cannot be empty" in str(exc_info.value)

    def test_whitespace_only_feedback_rejected(self):
        """Test that whitespace-only feedback is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate(feedback_text="   ")
        assert "Feedback text cannot be empty" in str(exc_info.value)

    def test_feedback_text_max_length(self):
        """Test that feedback text exceeding 10000 chars is rejected."""
        long_text = "x" * 10001
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate(feedback_text=long_text)
        assert "exceeds maximum length of 10,000 characters" in str(exc_info.value)

    def test_rating_validation_valid(self):
        """Test valid ratings (1-5)."""
        for rating in [1, 2, 3, 4, 5]:
            feedback = FeedbackCreate(feedback_text="Test", rating=rating)
            assert feedback.rating == rating

    def test_rating_validation_invalid_low(self):
        """Test rating below 1 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate(feedback_text="Test", rating=0)
        # Pydantic v2 uses "greater_than_equal" message
        assert "greater_than_equal" in str(exc_info.value) or "Rating must be between" in str(exc_info.value)

    def test_rating_validation_invalid_high(self):
        """Test rating above 5 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackCreate(feedback_text="Test", rating=6)
        # Pydantic v2 uses "less_than_equal" message
        assert "less_than_equal" in str(exc_info.value) or "Rating must be between" in str(exc_info.value)

    def test_optional_fields_default_to_none(self):
        """Test that optional metadata fields default to None."""
        feedback = FeedbackCreate(feedback_text="Test")
        assert feedback.feedback_id is None
        assert feedback.source is None
        assert feedback.created_at is None
        assert feedback.customer_segment is None
        assert feedback.product_area is None
        assert feedback.original_category is None


class TestFeedbackRecord:
    """Tests for FeedbackRecord model."""

    def test_feedback_record_creation(self):
        """Test creating a complete feedback record."""
        record = FeedbackRecord(
            feedback_id=1,
            product_id=1,
            external_id="EXT-123",
            content_hash="abc123",
            feedback_text="Test feedback",
            source="support_ticket",
            created_at=datetime(2024, 1, 15, 10, 30),
            customer_segment="enterprise",
            product_area="dashboard",
            rating=4,
            original_category="performance",
        )
        assert record.feedback_id == 1
        assert record.product_id == 1

    def test_feedback_record_validates_text(self):
        """Test that FeedbackRecord validates feedback_text."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackRecord(
                feedback_id=1,
                product_id=1,
                content_hash="abc123",
                feedback_text="",
            )
        assert "Feedback text cannot be empty" in str(exc_info.value)

    def test_feedback_record_validates_rating(self):
        """Test that FeedbackRecord validates rating."""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackRecord(
                feedback_id=1,
                product_id=1,
                content_hash="abc123",
                feedback_text="Test",
                rating=10,
            )
        # Pydantic v2 uses "less_than_equal" message
        assert "less_than_equal" in str(exc_info.value) or "Rating must be between" in str(exc_info.value)

    def test_from_create_method(self):
        """Test creating FeedbackRecord from FeedbackCreate."""
        create = FeedbackCreate(
            feedback_id="EXT-123",
            feedback_text="Test feedback",
            source="support_ticket",
        )
        content_hash = compute_content_hash(create.feedback_text)
        record = FeedbackRecord.from_create(create, product_id=1, content_hash=content_hash)

        assert record.external_id == "EXT-123"
        assert record.feedback_text == "Test feedback"
        assert record.source == "support_ticket"
        assert record.product_id == 1
        assert record.content_hash == content_hash
        assert record.feedback_id == 0  # Not set by database yet


class TestContentHash:
    """Tests for content hash computation."""

    def test_compute_content_hash_consistent(self):
        """Test that same text produces same hash."""
        text = "Test feedback content"
        hash1 = compute_content_hash(text)
        hash2 = compute_content_hash(text)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_content_hash_different_for_different_text(self):
        """Test that different text produces different hashes."""
        hash1 = compute_content_hash("Text one")
        hash2 = compute_content_hash("Text two")
        assert hash1 != hash2

    def test_compute_content_hash_strips_whitespace(self):
        """Test that hash computation strips whitespace."""
        hash1 = compute_content_hash("  Test  ")
        hash2 = compute_content_hash("Test")
        assert hash1 == hash2


class TestContentHashNormalization:
    """Tests for content hash normalization (F9)."""

    def test_identical_text_different_capitalization_same_hash(self):
        """Identical text with different capitalization produces the same hash."""
        hash1 = compute_content_hash("The dashboard is SLOW")
        hash2 = compute_content_hash("the dashboard is slow")
        hash3 = compute_content_hash("THE DASHBOARD IS SLOW")
        assert hash1 == hash2 == hash3

    def test_multiple_spaces_normalized(self):
        """Multiple spaces are normalized to single space."""
        hash1 = compute_content_hash("The    dashboard   is  slow")
        hash2 = compute_content_hash("The dashboard is slow")
        assert hash1 == hash2

    def test_leading_trailing_whitespace_removed(self):
        """Leading and trailing whitespace is removed."""
        hash1 = compute_content_hash("  The dashboard is slow  ")
        hash2 = compute_content_hash("The dashboard is slow")
        assert hash1 == hash2

    def test_tabs_and_newlines_normalized(self):
        """Tabs and newlines are normalized to single space."""
        hash1 = compute_content_hash("The\tdashboard\nis\tslow")
        hash2 = compute_content_hash("The dashboard is slow")
        assert hash1 == hash2

    def test_original_text_unchanged_in_record(self):
        """Original feedback text remains unchanged in FeedbackRecord."""
        from productsignal.models.feedback import FeedbackCreate, FeedbackRecord
        
        original_text = "  The DASHBOARD is   slow  "
        create = FeedbackCreate(feedback_text=original_text)
        content_hash = compute_content_hash(original_text)
        record = FeedbackRecord.from_create(create, product_id=1, content_hash=content_hash)
        
        # Original text preserved (with validation stripping)
        assert record.feedback_text == original_text.strip()
        # Hash is computed from normalized version
        assert record.content_hash == content_hash

    def test_deterministic_hash(self):
        """Hash calculation is deterministic."""
        text = "Test feedback with   multiple   spaces"
        hashes = [compute_content_hash(text) for _ in range(100)]
        assert all(h == hashes[0] for h in hashes)

    def test_no_automatic_deduplication(self):
        """Records with same content hash are NOT automatically deduplicated."""
        from productsignal.db.connection import execute_write, execute_query
        import tempfile
        from productsignal.db.connection import initialize_database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        
        try:
            initialize_database(db_path)
            
            product_id = execute_write(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("Test", "service_based", "saas", "saas"),
                db_path
            )
            
            feedback_text = "The dashboard is slow"
            content_hash = compute_content_hash(feedback_text)
            
            # Insert same feedback text twice with different external_ids
            execute_write(
                "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
                (product_id, "EXT-1", content_hash, feedback_text),
                db_path
            )
            execute_write(
                "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
                (product_id, "EXT-2", content_hash, feedback_text),
                db_path
            )
            
            # Both should exist - no automatic deduplication
            results = execute_query(
                "SELECT * FROM feedback WHERE product_id = ?",
                (product_id,),
                db_path,
                fetch="all"
            )
            assert len(results) == 2
            assert results[0]["external_id"] == "EXT-1"
            assert results[1]["external_id"] == "EXT-2"
            assert results[0]["content_hash"] == results[1]["content_hash"]
        finally:
            if db_path.exists():
                db_path.unlink()