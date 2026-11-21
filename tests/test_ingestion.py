"""
Tests for CSV Ingestion module.
"""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
import pandas as pd

from productsignal.ingestion.csv_ingestion import (
    CSVIngestion,
    load_csv,
    validate_csv_schema,
    map_row_to_feedback,
    construct_feedback_text,
    replace_placeholder,
    namespace_external_id,
    parse_timestamp,
    validate_rating,
    construct_original_category,
    generate_preview,
    insert_feedback_record,
    check_duplicate_import,
    count_repeated_content,
    EXPECTED_KAGGLE_COLUMNS,
    KAGGLE_COLUMN_MAP,
)
from productsignal.models.feedback import FeedbackCreate
from productsignal.product_context.repository import ProductContextCreate, get_repository, _repository as _global_repo
from productsignal.db.connection import initialize_database, execute_write


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        initialize_database(db_path)
        yield db_path
    finally:
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def active_product(temp_db):
    """Create an active product for testing."""
    # Reset global repository to use temp_db
    import productsignal.product_context.repository as repo_module
    repo_module._repository = None
    
    repo = get_repository(temp_db)
    create = ProductContextCreate(
        name="TestSaaS",
        product_type="service_based",
        category="saas",
        target_customers="SMBs",
        primary_use_case="Project management",
        vibe_key="saas",
    )
    product = repo.create_product(create)
    repo.set_active_product(product.product_id)
    return product


@pytest.fixture
def sample_csv():
    """Create a small synthetic CSV for testing."""
    data = {
        "Ticket ID": [1, 2, 3, 4, 5],
        "Customer Name": ["John Doe", "Jane Smith", "Bob Wilson", "Alice Brown", "Charlie Davis"],
        "Customer Email": ["john@example.com", "jane@example.com", "bob@example.com", "alice@example.com", "charlie@example.com"],
        "Customer Age": [30, 25, 40, 35, 28],
        "Customer Gender": ["Male", "Female", "Male", "Female", "Other"],
        "Product Purchased": ["Product A", "Product B", "Product A", "Product C", "Product B"],
        "Date of Purchase": ["2021-01-15", "2021-02-20", "2021-03-10", "2021-04-05", "2021-05-12"],
        "Ticket Type": ["Technical issue", "Billing inquiry", "Technical issue", "Refund request", "Technical issue"],
        "Ticket Subject": ["Product setup", "Payment issue", "Network problem", "Refund request", "Software bug"],
        "Ticket Description": [
            "I'm having an issue with the {product_purchased}. Please assist.",
            "I need help with billing for {product_purchased}.",
            "Network not working with {product_purchased}.",
            "Want refund for {product_purchased}.",
            "Software bug in {product_purchased}."
        ],
        "Ticket Status": ["Open", "Closed", "Pending Customer Response", "Closed", "Open"],
        "Resolution": ["Fixed", "Refunded", None, "Refunded", "Fixed"],
        "Ticket Priority": ["High", "Medium", "Critical", "Low", "High"],
        "Ticket Channel": ["Email", "Phone", "Chat", "Email", "Social media"],
        "First Response Time": ["2023-06-01 10:00:00", "2023-06-01 11:00:00", "2023-06-01 12:00:00", "2023-06-01 13:00:00", "2023-06-01 14:00:00"],
        "Time to Resolution": ["2023-06-01 11:00:00", "2023-06-01 12:00:00", None, "2023-06-01 14:00:00", "2023-06-01 15:00:00"],
        "Customer Satisfaction Rating": [4.0, 5.0, 3.0, 2.0, 4.0],
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df = pd.DataFrame(data)
        df.to_csv(f.name, index=False)
        csv_path = Path(f.name)

    yield csv_path

    if csv_path.exists():
        csv_path.unlink()


class TestCSVLoading:
    """Tests for CSV loading and schema validation."""

    def test_load_csv(self, sample_csv):
        """Test loading a CSV file."""
        df = load_csv(sample_csv)
        assert len(df) == 5
        assert set(df.columns) == EXPECTED_KAGGLE_COLUMNS

    def test_validate_csv_schema_valid(self, sample_csv):
        """Test schema validation passes for valid CSV."""
        df = load_csv(sample_csv)
        is_valid, issues = validate_csv_schema(df)
        assert is_valid
        assert len(issues) == 0

    def test_validate_csv_schema_missing_columns(self):
        """Test schema validation fails for missing columns."""
        df = pd.DataFrame({"Ticket ID": [1], "Wrong Column": ["test"]})
        is_valid, issues = validate_csv_schema(df)
        assert not is_valid
        assert any("Missing expected columns" in issue for issue in issues)

    def test_validate_csv_schema_empty(self):
        """Test schema validation fails for empty CSV."""
        df = pd.DataFrame(columns=list(EXPECTED_KAGGLE_COLUMNS))
        is_valid, issues = validate_csv_schema(df)
        assert not is_valid
        assert any("no data rows" in issue for issue in issues)


class TestFeedbackTextConstruction:
    """Tests for feedback text construction."""

    def test_construct_feedback_text_basic(self):
        """Test basic feedback text construction."""
        subject = "Product setup"
        description = "I'm having an issue with the product. Please help."
        product = "Product A"
        result = construct_feedback_text(subject, description, product)
        assert result == "Product setup: I'm having an issue with the product. Please help."

    def test_construct_feedback_text_placeholder_replacement(self):
        """Test placeholder replacement in feedback text."""
        subject = "Product setup"
        description = "I'm having an issue with the {product_purchased}. Please assist."
        product = "Product A"
        result = construct_feedback_text(subject, description, product)
        assert "Product A" in result
        assert "{product_purchased}" not in result

    def test_construct_feedback_text_multiple_placeholders(self):
        """Test multiple placeholder occurrences."""
        subject = "Issue"
        description = "Problem with {product_purchased}. Another issue with {product_purchased}."
        product = "Product X"
        result = construct_feedback_text(subject, description, product)
        assert result.count("Product X") == 2
        assert "{product_purchased}" not in result

    def test_construct_feedback_text_missing_subject(self):
        """Test with missing subject."""
        subject = ""
        description = "Just a description."
        product = "Product A"
        result = construct_feedback_text(subject, description, product)
        assert result == "Just a description."

    def test_construct_feedback_text_missing_description(self):
        """Test with missing description."""
        subject = "Subject only"
        description = ""
        product = "Product A"
        result = construct_feedback_text(subject, description, product)
        assert result == "Subject only"

    def test_construct_feedback_text_both_missing(self):
        """Test with both missing."""
        result = construct_feedback_text("", "", "Product A")
        assert result == ""

    def test_replace_placeholder(self):
        """Test placeholder replacement function."""
        desc = "Issue with {product_purchased} and {product_purchased}."
        result = replace_placeholder(desc, "Product A")
        assert result == "Issue with Product A and Product A."

    def test_replace_placeholder_no_placeholder(self):
        """Test replacement when no placeholder exists."""
        desc = "Just a description."
        result = replace_placeholder(desc, "Product A")
        assert result == "Just a description."

    def test_replace_placeholder_none_product(self):
        """Test replacement with None product."""
        desc = "Issue with {product_purchased}."
        result = replace_placeholder(desc, None)
        assert result == "Issue with {product_purchased}."


class TestExternalIdNamespacing:
    """Tests for external ID namespacing."""

    def test_namespace_external_id_integer(self):
        """Test namespacing integer ticket ID."""
        result = namespace_external_id(123)
        assert result == "kaggle_support:123"

    def test_namespace_external_id_string(self):
        """Test namespacing string ticket ID."""
        result = namespace_external_id("ABC-123")
        assert result == "kaggle_support:ABC-123"

    def test_namespace_external_id_whitespace(self):
        """Test namespacing handles whitespace."""
        result = namespace_external_id("  123  ")
        assert result == "kaggle_support:123"


class TestTimestampParsing:
    """Tests for timestamp parsing."""

    def test_parse_timestamp_valid(self):
        """Test parsing valid timestamp."""
        result = parse_timestamp("2023-06-01 12:15:36")
        assert result == datetime(2023, 6, 1, 12, 15, 36)

    def test_parse_timestamp_none(self):
        """Test parsing None."""
        result = parse_timestamp(None)
        assert result is None

    def test_parse_timestamp_empty(self):
        """Test parsing empty string."""
        result = parse_timestamp("")
        assert result is None

    def test_parse_timestamp_nan(self):
        """Test parsing NaN."""
        result = parse_timestamp(float('nan'))
        assert result is None

    def test_parse_timestamp_invalid(self):
        """Test parsing invalid format."""
        result = parse_timestamp("invalid")
        assert result is None


class TestRatingValidation:
    """Tests for rating validation."""

    def test_validate_rating_valid_int(self):
        """Test valid integer rating."""
        assert validate_rating(4) == 4
        assert validate_rating(1) == 1
        assert validate_rating(5) == 5

    def test_validate_rating_valid_float_integer(self):
        """Test valid float that is integer."""
        assert validate_rating(4.0) == 4
        assert validate_rating(3.0) == 3

    def test_validate_rating_invalid_fractional(self):
        """Test fractional rating is rejected."""
        assert validate_rating(4.5) is None
        assert validate_rating(3.7) is None

    def test_validate_rating_out_of_range(self):
        """Test out of range ratings."""
        assert validate_rating(0) is None
        assert validate_rating(6) is None
        assert validate_rating(-1) is None

    def test_validate_rating_none(self):
        """Test None rating."""
        assert validate_rating(None) is None

    def test_validate_rating_nan(self):
        """Test NaN rating."""
        assert validate_rating(float('nan')) is None


class TestOriginalCategoryConstruction:
    """Tests for original category construction."""

    def test_construct_original_category_both(self):
        """Test with both type and subject."""
        result = construct_original_category("Technical issue", "Product setup")
        assert result == "Technical issue - Product setup"

    def test_construct_original_category_type_only(self):
        """Test with only type."""
        result = construct_original_category("Technical issue", "")
        assert result == "Technical issue"

    def test_construct_original_category_subject_only(self):
        """Test with only subject."""
        result = construct_original_category("", "Product setup")
        assert result == "Product setup"

    def test_construct_original_category_both_empty(self):
        """Test with both empty."""
        result = construct_original_category("", "")
        assert result == "Unknown"


class TestRowMapping:
    """Tests for row mapping to FeedbackCreate."""

    def test_map_row_valid(self, active_product):
        """Test mapping a valid row."""
        product_id = active_product.product_id
        row = pd.Series({
            "Ticket ID": 1,
            "Ticket Subject": "Product setup",
            "Ticket Description": "Issue with {product_purchased}.",
            "Ticket Channel": "Email",
            "First Response Time": "2023-06-01 10:00:00",
            "Customer Satisfaction Rating": 4.0,
            "Ticket Type": "Technical issue",
            "Ticket Subject": "Product setup",
            "Product Purchased": "Product A",
        })

        feedback, error = map_row_to_feedback(row, product_id)
        assert feedback is not None
        assert error is None
        assert feedback.feedback_id == "kaggle_support:1"
        assert "Product A" in feedback.feedback_text
        assert feedback.source == "Email"
        assert feedback.rating == 4
        assert feedback.original_category == "Technical issue - Product setup"

    def test_map_row_missing_ticket_id(self, active_product):
        """Test mapping row with missing Ticket ID."""
        product_id = active_product.product_id
        row = pd.Series({
            "Ticket ID": None,
            "Ticket Subject": "Product setup",
            "Ticket Description": "Issue.",
            "Ticket Channel": "Email",
        })

        feedback, error = map_row_to_feedback(row, product_id)
        assert feedback is None
        assert "Missing Ticket ID" in error

    def test_map_row_empty_feedback(self, active_product):
        """Test mapping row with empty feedback text."""
        product_id = active_product.product_id
        row = pd.Series({
            "Ticket ID": 1,
            "Ticket Subject": "",
            "Ticket Description": "",
            "Ticket Channel": "Email",
        })

        feedback, error = map_row_to_feedback(row, product_id)
        assert feedback is None
        assert "Empty feedback text" in error

    def test_map_row_fractional_rating(self, active_product):
        """Test mapping row with fractional rating becomes None."""
        product_id = active_product.product_id
        row = pd.Series({
            "Ticket ID": 1,
            "Ticket Subject": "Test",
            "Ticket Description": "Test",
            "Ticket Channel": "Email",
            "Customer Satisfaction Rating": 4.5,
        })

        feedback, error = map_row_to_feedback(row, product_id)
        assert feedback is not None
        assert feedback.rating is None  # Fractional -> None

    def test_map_row_missing_timestamp(self, active_product):
        """Test mapping row with missing timestamp."""
        product_id = active_product.product_id
        row = pd.Series({
            "Ticket ID": 1,
            "Ticket Subject": "Test",
            "Ticket Description": "Test",
            "Ticket Channel": "Email",
            "First Response Time": None,
        })

        feedback, error = map_row_to_feedback(row, product_id)
        assert feedback is not None
        assert feedback.created_at is None


class TestPreviewGeneration:
    """Tests for preview generation."""

    def test_generate_preview(self, temp_db, sample_csv, active_product):
        """Test preview generation."""
        df = load_csv(sample_csv)
        product_id = active_product.product_id

        preview = generate_preview(df, product_id, temp_db)

        assert preview.total_rows == 5
        assert preview.dataset_recognized
        assert preview.validation_summary["valid"] == 5
        assert preview.validation_summary["rejected"] == 0
        assert len(preview.sample_records) == 5
        assert len(preview.pii_excluded) == 4
        assert "Customer Name" in preview.pii_excluded

    def test_generate_preview_repeated_content(self, temp_db, active_product):
        """Test preview with repeated content."""
        # Create data with duplicate feedback
        data = {
            "Ticket ID": [1, 2, 3],
            "Ticket Subject": ["Test", "Test", "Different"],
            "Ticket Description": ["Same desc", "Same desc", "Other desc"],
            "Product Purchased": ["Prod A", "Prod A", "Prod B"],
            "Ticket Channel": ["Email", "Email", "Email"],
            "First Response Time": ["2023-06-01 10:00:00"] * 3,
            "Customer Satisfaction Rating": [4.0, 4.0, 4.0],
            "Ticket Type": ["Technical issue"] * 3,
            "Ticket Subject": ["Test", "Test", "Different"],
        }
        df = pd.DataFrame(data)
        product_id = active_product.product_id

        preview = generate_preview(df, product_id, temp_db)
        # Two rows share same normalized content
        assert preview.repeated_content_count == 2


class TestImport:
    """Tests for CSV import."""

    def test_import_valid_csv(self, temp_db, sample_csv, active_product):
        """Test importing a valid CSV."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        result = ingestion.import_csv(sample_csv)

        assert result.total_rows == 5
        assert result.imported == 5
        assert result.rejected == 0
        assert result.duplicate_imports == 0

        # Verify records in database
        from productsignal.db.connection import execute_query
        count = execute_query(
            "SELECT COUNT(*) as count FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="one"
        )["count"]
        assert count == 5

    def test_import_rejects_invalid_rows(self, temp_db, active_product):
        """Test import rejects invalid rows but imports valid ones."""
        product_id = active_product.product_id

        # Create CSV with mix of valid and invalid
        # Row 1: Valid
        # Row 2: Empty subject AND empty description -> should be rejected
        # Row 3: Valid
        data = {
            "Ticket ID": [1, 2, 3],
            "Ticket Subject": ["Valid", "", "Valid2"],
            "Ticket Description": ["Good desc", "", "Good desc2"],
            "Product Purchased": ["Prod A", "Prod B", "Prod C"],
            "Ticket Channel": ["Email"] * 3,
            "First Response Time": ["2023-06-01 10:00:00"] * 3,
            "Customer Satisfaction Rating": [4.0, 4.0, 4.0],
            "Ticket Type": ["Technical issue"] * 3,
            "Ticket Subject": ["Valid", "", "Valid2"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.total_rows == 3
            assert result.imported == 2
            assert result.rejected == 1
            assert any("Empty feedback text" in e["reason"] for e in result.errors)
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_import_duplicate_external_id_prevented(self, temp_db, sample_csv, active_product):
        """Test duplicate external_id imports are prevented."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        # First import
        result1 = ingestion.import_csv(sample_csv)
        assert result1.imported == 5

        # Second import of same CSV
        result2 = ingestion.import_csv(sample_csv)
        assert result2.imported == 0
        assert result2.duplicate_imports == 5

        # Verify database still has only 5 records
        from productsignal.db.connection import execute_query
        count = execute_query(
            "SELECT COUNT(*) as count FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="one"
        )["count"]
        assert count == 5

    def test_import_missing_active_product(self, temp_db, sample_csv):
        """Test import fails gracefully with no active product."""
        # Create ingestion with non-existent product ID
        ingestion = CSVIngestion(99999, temp_db)

        result = ingestion.import_csv(sample_csv)

        # Should fail due to foreign key constraint
        assert result.imported == 0
        assert result.rejected > 0 or result.errors

    def test_import_preserves_repeated_content(self, temp_db, active_product):
        """Test that repeated feedback content is preserved (not deduplicated)."""
        product_id = active_product.product_id

        # Create CSV with same feedback text but different external IDs
        data = {
            "Ticket ID": [1, 2],
            "Ticket Subject": ["Test", "Test"],
            "Ticket Description": ["Same description", "Same description"],
            "Product Purchased": ["Prod A", "Prod A"],
            "Ticket Channel": ["Email", "Email"],
            "First Response Time": ["2023-06-01 10:00:00", "2023-06-01 11:00:00"],
            "Customer Satisfaction Rating": [4.0, 4.0],
            "Ticket Type": ["Technical issue", "Technical issue"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.imported == 2

            # Verify both records exist with same content_hash
            from productsignal.db.connection import execute_query
            rows = execute_query(
                "SELECT external_id, content_hash, feedback_text FROM feedback WHERE product_id = ?",
                (product_id,), db_path=temp_db, fetch="all"
            )
            assert len(rows) == 2
            assert rows[0]["content_hash"] == rows[1]["content_hash"]
            assert rows[0]["feedback_text"] == rows[1]["feedback_text"]
            assert rows[0]["external_id"] != rows[1]["external_id"]
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestDuplicateImportPrevention:
    """Tests for duplicate import prevention."""

    def test_check_duplicate_import(self, temp_db, sample_csv, active_product):
        """Test duplicate import check."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        # First import
        ingestion.import_csv(sample_csv)

        # Check duplicates - need to use connection
        from productsignal.db.connection import get_connection
        with get_connection(temp_db) as conn:
            from productsignal.ingestion.csv_ingestion import check_duplicate_import
            assert check_duplicate_import(conn, product_id, "kaggle_support:1")
            assert not check_duplicate_import(conn, product_id, "kaggle_support:999")

    def test_reimport_idempotency(self, temp_db, sample_csv, active_product):
        """Test re-import is idempotent."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        # Import multiple times
        for i in range(3):
            result = ingestion.import_csv(sample_csv)
            if i == 0:
                assert result.imported == 5
            else:
                assert result.imported == 0
                assert result.duplicate_imports == 5


class TestTransactionRollback:
    """Tests for transaction rollback on failure."""

    def test_rollback_on_failure(self, temp_db, active_product):
        """Test transaction rolls back on unexpected database failure during import.

        This test injects a genuine sqlite3.OperationalError on the third
        insertion attempt and verifies that the entire transaction is rolled back,
        leaving the database unchanged.
        """
        import sqlite3
        from unittest.mock import patch

        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        # Insert two pre-existing records directly into the database
        from productsignal.db.connection import execute_write
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text, source, created_at, rating, original_category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, "kaggle_support:pre1", "hash1", "Pre-existing record 1", "Email", "2023-06-01 10:00:00", 4, "Technical issue - Test"),
            temp_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text, source, created_at, rating, original_category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, "kaggle_support:pre2", "hash2", "Pre-existing record 2", "Email", "2023-06-01 11:00:00", 5, "Technical issue - Test"),
            temp_db
        )

        # Verify pre-existing records
        from productsignal.db.connection import execute_query
        count_before = execute_query(
            "SELECT COUNT(*) as count FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="one"
        )["count"]
        assert count_before == 2

        # Prepare five genuinely new records with unique external IDs
        import tempfile
        data = {
            "Ticket ID": [10, 11, 12, 13, 14],
            "Ticket Subject": ["Test1", "Test2", "Test3", "Test4", "Test5"],
            "Ticket Description": ["Desc1", "Desc2", "Desc3", "Desc4", "Desc5"],
            "Product Purchased": ["Prod A", "Prod B", "Prod C", "Prod D", "Prod E"],
            "Ticket Channel": ["Email"] * 5,
            "First Response Time": ["2023-06-01 12:00:00"] * 5,
            "Customer Satisfaction Rating": [4.0] * 5,
            "Ticket Type": ["Technical issue"] * 5,
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)

            # Monkeypatch insert_feedback_record to fail on the third call
            import productsignal.ingestion.csv_ingestion as csv_ingestion_module
            original_insert = csv_ingestion_module.insert_feedback_record
            call_count = [0]

            def failing_insert(conn, feedback, product_id, content_hash):
                call_count[0] += 1
                if call_count[0] == 3:
                    raise sqlite3.OperationalError("disk I/O error")
                return original_insert(conn, feedback, product_id, content_hash)

            with patch('productsignal.ingestion.csv_ingestion.insert_feedback_record', side_effect=failing_insert):
                ingestion = CSVIngestion(product_id, temp_db)
                result = ingestion.import_csv(csv_path)

        finally:
            if csv_path.exists():
                csv_path.unlink()

        # Verify the import reports failure
        assert result.imported == 0, "No records should be imported on transaction failure"
        assert result.rejected == 5, "All 5 records should be marked as rejected"
        assert len(result.errors) > 0, "Should have transaction failure error"
        assert "Transaction failed" in result.errors[0]["reason"]
        assert "disk I/O error" in result.errors[0]["reason"]

        # Verify zero of the five new records persist
        # external_id format is "kaggle_support:{id}"; the prefix is 15 chars,
        # so SUBSTR from position 16 extracts the numeric portion.
        from productsignal.db.connection import execute_query
        new_count = execute_query(
            "SELECT COUNT(*) as count FROM feedback WHERE product_id = ? AND external_id LIKE 'kaggle_support:%' AND CAST(SUBSTR(external_id, 16) AS INTEGER) >= 10",
            (product_id,), db_path=temp_db, fetch="one"
        )["count"]
        assert new_count == 0, "Zero new records should persist after rollback"

        # Verify both pre-existing records remain unchanged
        count_after = execute_query(
            "SELECT COUNT(*) as count FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="one"
        )["count"]
        assert count_after == 2, "Pre-existing records must remain unchanged"

        # Verify specific pre-existing records are intact
        pre_records = execute_query(
            "SELECT external_id, feedback_text FROM feedback WHERE product_id = ? AND external_id IN ('kaggle_support:pre1', 'kaggle_support:pre2')",
            (product_id,), db_path=temp_db, fetch="all"
        )
        assert len(pre_records) == 2
        assert {r["external_id"] for r in pre_records} == {"kaggle_support:pre1", "kaggle_support:pre2"}
        assert {r["feedback_text"] for r in pre_records} == {"Pre-existing record 1", "Pre-existing record 2"}

    def test_duplicate_external_ids_counted_as_duplicates(self, temp_db, active_product, sample_csv):
        """Test that duplicate external IDs are counted as duplicates, not errors."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)

        # First import
        ingestion.import_csv(sample_csv)

        # Second import - should count as duplicates, not errors
        result = ingestion.import_csv(sample_csv)
        assert result.duplicate_imports == 5
        assert result.errors == []

    def test_validation_failures_rejected_without_rollback(self, temp_db, active_product):
        """Test that validation failures are rejected without rolling back valid rows."""
        product_id = active_product.product_id

        # Create CSV with mix of valid and invalid (empty feedback)
        data = {
            "Ticket ID": [1, 2, 3],
            "Ticket Subject": ["Valid", "", "Valid2"],
            "Ticket Description": ["Good desc", "", "Good desc2"],
            "Product Purchased": ["Prod A", "Prod B", "Prod C"],
            "Ticket Channel": ["Email"] * 3,
            "First Response Time": ["2023-06-01 10:00:00"] * 3,
            "Customer Satisfaction Rating": [4.0, 4.0, 4.0],
            "Ticket Type": ["Technical issue"] * 3,
            "Ticket Subject": ["Valid", "", "Valid2"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.total_rows == 3
            assert result.imported == 2
            assert result.rejected == 1
            assert any("Empty feedback text" in e["reason"] for e in result.errors)
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestContentHash:
    """Tests for content hash and repeated content."""

    def test_repeated_content_preserved(self, temp_db, active_product):
        """Test that repeated content is preserved, not deduplicated."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1, 2, 3],
            "Ticket Subject": ["Test", "Test", "Different"],
            "Ticket Description": ["Same desc", "Same desc", "Other desc"],
            "Product Purchased": ["Prod A", "Prod A", "Prod B"],
            "Ticket Channel": ["Email"] * 3,
            "First Response Time": ["2023-06-01 10:00:00"] * 3,
            "Customer Satisfaction Rating": [4.0, 4.0, 4.0],
            "Ticket Type": ["Technical issue"] * 3,
            "Ticket Subject": ["Test", "Test", "Different"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.imported == 3

            from productsignal.db.connection import execute_query
            rows = execute_query(
                "SELECT external_id, content_hash, feedback_text FROM feedback WHERE product_id = ?",
                (product_id,), db_path=temp_db, fetch="all"
            )
            # First two should have same content hash
            assert rows[0]["content_hash"] == rows[1]["content_hash"]
            assert rows[2]["content_hash"] != rows[0]["content_hash"]
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestPIIExclusion:
    """Tests that PII is never stored."""

    def test_pii_not_in_feedback_text(self, temp_db, sample_csv, active_product):
        """Test PII fields don't appear in feedback text."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)
        ingestion.import_csv(sample_csv)

        from productsignal.db.connection import execute_query
        rows = execute_query(
            "SELECT feedback_text FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="all"
        )

        for row in rows:
            text = row["feedback_text"]
            # Check no email-like patterns
            assert "@" not in text
            # Check no name-like patterns (from our test data)
            assert "John Doe" not in text
            assert "Jane Smith" not in text


class TestRatingFractional:
    """Tests for fractional rating handling."""

    def test_fractional_rating_reported(self, temp_db, active_product):
        """Test fractional ratings are counted and set to NULL."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1, 2],
            "Ticket Subject": ["Test", "Test2"],
            "Ticket Description": ["Desc", "Desc2"],
            "Product Purchased": ["Prod A", "Prod B"],
            "Ticket Channel": ["Email", "Email"],
            "First Response Time": ["2023-06-01 10:00:00"] * 2,
            "Customer Satisfaction Rating": [4.5, 4.0],  # One fractional
            "Ticket Type": ["Technical issue", "Technical issue"],
            "Ticket Subject": ["Test", "Test2"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            df = load_csv(csv_path)
            preview = generate_preview(df, product_id, temp_db)
            assert preview.data_quality["fractional_ratings"] == 1

            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            from productsignal.db.connection import execute_query
            rows = execute_query(
                "SELECT rating FROM feedback WHERE product_id = ? ORDER BY external_id",
                (product_id,), db_path=temp_db, fetch="all"
            )
            # First record had fractional rating -> NULL
            assert rows[0]["rating"] is None
            # Second had valid rating
            assert rows[1]["rating"] == 4
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestOriginalCategoryConstruction:
    """Tests for original_category in imported records."""

    def test_original_category_stored(self, temp_db, sample_csv, active_product):
        """Test original_category is constructed and stored."""
        product_id = active_product.product_id
        ingestion = CSVIngestion(product_id, temp_db)
        ingestion.import_csv(sample_csv)

        from productsignal.db.connection import execute_query
        rows = execute_query(
            "SELECT original_category FROM feedback WHERE product_id = ?",
            (product_id,), db_path=temp_db, fetch="all"
        )

        for row in rows:
            cat = row["original_category"]
            assert " - " in cat  # Format: "Type - Subject"
            assert cat != "Unknown"


class TestTimestampPolicy:
    """Tests for timestamp handling policy."""

    def test_created_at_none_when_missing(self, temp_db, active_product):
        """Test created_at is NULL when First Response Time missing."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1],
            "Ticket Subject": ["Test"],
            "Ticket Description": ["Desc"],
            "Product Purchased": ["Prod A"],
            "Ticket Channel": ["Email"],
            "First Response Time": [None],
            "Customer Satisfaction Rating": [4.0],
            "Ticket Type": ["Technical issue"],
            "Ticket Subject": ["Test"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            ingestion.import_csv(csv_path)

            from productsignal.db.connection import execute_query
            row = execute_query(
                "SELECT created_at FROM feedback WHERE product_id = ?",
                (product_id,), db_path=temp_db, fetch="one"
            )
            assert row["created_at"] is None
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_timestamp_not_fallback_to_purchase(self, temp_db, active_product):
        """Test Date of Purchase is NOT used as fallback for created_at."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1],
            "Ticket Subject": ["Test"],
            "Ticket Description": ["Desc"],
            "Product Purchased": ["Prod A"],
            "Ticket Channel": ["Email"],
            "First Response Time": [None],
            "Date of Purchase": ["2021-01-15"],
            "Customer Satisfaction Rating": [4.0],
            "Ticket Type": ["Technical issue"],
            "Ticket Subject": ["Test"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            ingestion.import_csv(csv_path)

            from productsignal.db.connection import execute_query
            row = execute_query(
                "SELECT created_at FROM feedback WHERE product_id = ?",
                (product_id,), db_path=temp_db, fetch="one"
            )
            # created_at should be NULL, not the purchase date
            assert row["created_at"] is None
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestMissingOptionalFields:
    """Tests that optional missing fields don't cause rejection."""

    def test_missing_rating_not_rejected(self, temp_db, active_product):
        """Test missing rating doesn't cause rejection."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1],
            "Ticket Subject": ["Test"],
            "Ticket Description": ["Desc"],
            "Product Purchased": ["Prod A"],
            "Ticket Channel": ["Email"],
            "First Response Time": ["2023-06-01 10:00:00"],
            "Customer Satisfaction Rating": [None],
            "Ticket Type": ["Technical issue"],
            "Ticket Subject": ["Test"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.imported == 1
            assert result.rejected == 0

            from productsignal.db.connection import execute_query
            row = execute_query(
                "SELECT rating FROM feedback WHERE product_id = ?",
                (product_id,), db_path=temp_db, fetch="one"
            )
            assert row["rating"] is None
        finally:
            if csv_path.exists():
                csv_path.unlink()

    def test_missing_timestamp_not_rejected(self, temp_db, active_product):
        """Test missing timestamp doesn't cause rejection."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1],
            "Ticket Subject": ["Test"],
            "Ticket Description": ["Desc"],
            "Product Purchased": ["Prod A"],
            "Ticket Channel": ["Email"],
            "First Response Time": [None],
            "Customer Satisfaction Rating": [4.0],
            "Ticket Type": ["Technical issue"],
            "Ticket Subject": ["Test"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            pd.DataFrame(data).to_csv(f.name, index=False)
            csv_path = Path(f.name)

        try:
            ingestion = CSVIngestion(product_id, temp_db)
            result = ingestion.import_csv(csv_path)

            assert result.imported == 1
            assert result.rejected == 0
        finally:
            if csv_path.exists():
                csv_path.unlink()


class TestCountRepeatedContent:
    """Tests for repeated content counting."""

    def test_count_repeated_content(self, temp_db, active_product):
        """Test counting rows with repeated normalized content."""
        product_id = active_product.product_id

        data = {
            "Ticket ID": [1, 2, 3, 4],
            "Ticket Subject": ["Test", "Test", "Different", "Different"],
            "Ticket Description": ["Same", "Same", "Other", "Other"],
            "Product Purchased": ["Prod A"] * 4,
            "Ticket Channel": ["Email"] * 4,
            "First Response Time": ["2023-06-01 10:00:00"] * 4,
            "Customer Satisfaction Rating": [4.0] * 4,
            "Ticket Type": ["Technical issue"] * 4,
        }
        df = pd.DataFrame(data)

        repeated = count_repeated_content(df)
        # All 4 rows share content with at least one other
        assert repeated == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])