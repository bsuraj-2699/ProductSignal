"""
CSV Ingestion module for ProductSignal.

Handles dataset-specific CSV loading, validation, preview, and import.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from productsignal.db.connection import get_connection
from productsignal.models.feedback import (
    FeedbackCreate,
    FeedbackRecord,
    compute_content_hash,
    normalize_feedback_text,
)


logger = logging.getLogger(__name__)


# Expected Kaggle schema columns
EXPECTED_KAGGLE_COLUMNS = {
    "Ticket ID",
    "Customer Name",
    "Customer Email",
    "Customer Age",
    "Customer Gender",
    "Product Purchased",
    "Date of Purchase",
    "Ticket Type",
    "Ticket Subject",
    "Ticket Description",
    "Ticket Status",
    "Resolution",
    "Ticket Priority",
    "Ticket Channel",
    "First Response Time",
    "Time to Resolution",
    "Customer Satisfaction Rating",
}


@dataclass
class IngestionResult:
    """Result of a CSV import operation."""
    total_rows: int = 0
    imported: int = 0
    rejected: int = 0
    duplicate_imports: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreviewResult:
    """Result of a CSV preview operation."""
    total_rows: int
    columns: list[str]
    column_mapping: dict[str, str]
    sample_records: list[dict[str, Any]]
    data_quality: dict[str, Any]
    validation_summary: dict[str, int]
    repeated_content_count: int
    pii_excluded: list[str]
    timestamp_policy_note: str
    dataset_recognized: bool


# Column mapping from CSV to internal fields
KAGGLE_COLUMN_MAP = {
    "Ticket ID": "ticket_id",
    "Ticket Subject": "subject",
    "Ticket Description": "description",
    "Ticket Channel": "channel",
    "First Response Time": "first_response_time",
    "Date of Purchase": "purchase_date",
    "Customer Satisfaction Rating": "satisfaction_rating",
    "Ticket Type": "ticket_type",
    "Ticket Status": "status",
    "Ticket Priority": "priority",
    "Product Purchased": "product_purchased",
    "Customer Name": "customer_name",
    "Customer Email": "customer_email",
    "Customer Age": "customer_age",
    "Customer Gender": "customer_gender",
    "Resolution": "resolution",
    "Time to Resolution": "time_to_resolution",
}


def load_csv(file_path: Path | str) -> pd.DataFrame:
    """
    Load CSV file into a DataFrame.

    Args:
        file_path: Path to the CSV file.

    Returns:
        DataFrame with the CSV data.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # Read with pandas for robust CSV parsing
    df = pd.read_csv(path)
    return df


def validate_csv_schema(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Validate that the CSV has the expected Kaggle schema.

    Args:
        df: DataFrame to validate.

    Returns:
        Tuple of (is_valid, list_of_issues).
    """
    issues = []
    columns = set(df.columns)

    missing = EXPECTED_KAGGLE_COLUMNS - columns
    if missing:
        issues.append(f"Missing expected columns: {sorted(missing)}")

    extra = columns - EXPECTED_KAGGLE_COLUMNS
    if extra:
        issues.append(f"Unexpected extra columns: {sorted(extra)}")

    if len(df) == 0:
        issues.append("CSV contains no data rows")

    # Check Ticket ID column exists and has data
    if "Ticket ID" in df.columns:
        if df["Ticket ID"].isna().all():
            issues.append("Ticket ID column is all null")
    else:
        issues.append("Ticket ID column missing")

    return len(issues) == 0, issues


def replace_placeholder(description: str, product_name: str) -> str:
    """
    Replace {product_purchased} placeholder with actual product name.

    Args:
        description: Raw description text.
        product_name: Product name from 'Product Purchased' column.

    Returns:
        Description with placeholder replaced.
    """
    if not isinstance(description, str):
        return str(description) if description is not None else ""
    if not isinstance(product_name, str):
        return description

    return description.replace("{product_purchased}", product_name)


def construct_feedback_text(subject: Any, description: Any, product_name: Any) -> str:
    """
    Construct feedback text from subject and description.

    Args:
        subject: Ticket Subject.
        description: Ticket Description with placeholder replaced.
        product_name: Product name for placeholder replacement.

    Returns:
        Constructed feedback text.
    """
    # Handle NaN/None values
    if subject is None or (isinstance(subject, float) and pd.isna(subject)):
        subject = ""
    if description is None or (isinstance(description, float) and pd.isna(description)):
        description = ""
    if product_name is None or (isinstance(product_name, float) and pd.isna(product_name)):
        product_name = ""

    subject = str(subject).strip()
    description = str(description).strip()
    product_name = str(product_name)

    # Replace placeholder
    description = replace_placeholder(description, product_name)

    if not subject and not description:
        return ""

    if subject and description:
        return f"{subject}: {description}"
    elif subject:
        return subject
    else:
        return description


def namespace_external_id(ticket_id: Any) -> str:
    """
    Namespace external ID to avoid collisions across datasets.

    Args:
        ticket_id: Raw ticket ID from CSV.

    Returns:
        Namespaced external ID string.
    """
    return f"kaggle_support:{str(ticket_id).strip()}"


def parse_timestamp(timestamp_str: Any) -> Optional[datetime]:
    """
    Parse timestamp string to datetime.

    Expected format: YYYY-MM-DD HH:MM:SS

    Args:
        timestamp_str: Timestamp string from CSV.

    Returns:
        Parsed datetime or None if unparseable.
    """
    if timestamp_str is None or (isinstance(timestamp_str, float) and pd.isna(timestamp_str)):
        return None

    timestamp_str = str(timestamp_str).strip()
    if not timestamp_str:
        return None

    try:
        # Parse as naive datetime (assumed UTC)
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning(f"Failed to parse timestamp: {timestamp_str}")
        return None


def validate_rating(rating_value: Any) -> Optional[int]:
    """
    Validate and convert rating to integer 1-5.

    Does not use round() - only accepts values that are already
    integer-valued or can be safely converted without rounding.

    Args:
        rating_value: Rating value from CSV.

    Returns:
        Integer rating 1-5, or None if invalid.
    """
    if rating_value is None or (isinstance(rating_value, float) and pd.isna(rating_value)):
        return None

    try:
        # Check if it's already an integer value
        if isinstance(rating_value, (int, float)):
            if isinstance(rating_value, float) and not rating_value.is_integer():
                # Fractional rating - reject
                return None
            rating_int = int(rating_value)
        else:
            rating_int = int(str(rating_value).strip())

        if 1 <= rating_int <= 5:
            return rating_int
    except (ValueError, TypeError):
        pass

    return None


def construct_original_category(ticket_type: Any, ticket_subject: Any) -> str:
    """
    Construct original_category from ticket type and subject.

    Format: "{Ticket Type} - {Ticket Subject}"

    Args:
        ticket_type: Ticket Type from CSV.
        ticket_subject: Ticket Subject from CSV.

    Returns:
        Constructed category string.
    """
    # Handle NaN/None values
    if ticket_type is None or (isinstance(ticket_type, float) and pd.isna(ticket_type)):
        ticket_type = ""
    if ticket_subject is None or (isinstance(ticket_subject, float) and pd.isna(ticket_subject)):
        ticket_subject = ""

    ticket_type = str(ticket_type).strip()
    ticket_subject = str(ticket_subject).strip()

    parts = []
    if ticket_type:
        parts.append(ticket_type)
    if ticket_subject:
        parts.append(ticket_subject)

    return " - ".join(parts) if parts else "Unknown"


def map_row_to_feedback(row: pd.Series, product_id: int) -> tuple[Optional[FeedbackCreate], Optional[str]]:
    """
    Map a CSV row to a FeedbackCreate model.

    Args:
        row: DataFrame row (Series).
        product_id: Active product ID.

    Returns:
        Tuple of (FeedbackCreate or None, error message or None).
    """
    try:
        # Extract fields
        ticket_id = row.get("Ticket ID")
        subject = row.get("Ticket Subject")
        description = row.get("Ticket Description")
        channel = row.get("Ticket Channel")
        first_response_time = row.get("First Response Time")
        satisfaction_rating = row.get("Customer Satisfaction Rating")
        ticket_type = row.get("Ticket Type")
        ticket_subject = row.get("Ticket Subject")
        product_purchased = row.get("Product Purchased")

        # Validate required fields
        if pd.isna(ticket_id) or ticket_id is None:
            return None, "Missing Ticket ID"

        external_id = namespace_external_id(ticket_id)

        # Construct feedback text
        feedback_text = construct_feedback_text(subject, description, product_purchased)
        if not feedback_text or not feedback_text.strip():
            return None, "Empty feedback text after construction"

        # Parse timestamp (keep NULL by default per policy)
        created_at = parse_timestamp(first_response_time)

        # Validate rating
        rating = validate_rating(satisfaction_rating)

        # Construct original category
        original_category = construct_original_category(ticket_type, ticket_subject)

        # Source from channel
        source = str(channel).strip() if channel and not pd.isna(channel) else None

        # Create FeedbackCreate
        feedback_create = FeedbackCreate(
            feedback_id=external_id,
            feedback_text=feedback_text.strip(),
            source=source,
            created_at=created_at,
            customer_segment=None,  # Not derived from PII
            product_area=None,      # Not applicable for this dataset
            rating=rating,
            original_category=original_category,
        )

        return feedback_create, None

    except Exception as e:
        logger.exception(f"Error mapping row: {e}")
        return None, f"Mapping error: {e}"


def check_duplicate_import(conn: sqlite3.Connection, product_id: int, external_id: str) -> bool:
    """
    Check if a record with this external_id already exists for the product.

    Args:
        conn: Database connection (shared transaction).
        product_id: Product ID.
        external_id: External ID to check.

    Returns:
        True if record exists (duplicate import), False otherwise.
    """
    result = conn.execute(
        "SELECT 1 FROM feedback WHERE product_id = ? AND external_id = ? LIMIT 1",
        (product_id, external_id),
    ).fetchone()
    return result is not None


def insert_feedback_record(conn: sqlite3.Connection, feedback: FeedbackCreate, product_id: int, content_hash: str) -> int:
    """
    Insert a feedback record into the database using shared connection.

    Args:
        conn: Database connection (shared transaction).
        feedback: Validated FeedbackCreate model.
        product_id: Product ID.
        content_hash: Pre-computed content hash.

    Returns:
        New feedback_id.

    Raises:
        sqlite3.IntegrityError: If duplicate external_id for product.
    """
    record = FeedbackRecord.from_create(feedback, product_id, content_hash)

    cursor = conn.execute(
        """
        INSERT INTO feedback (
            product_id, external_id, content_hash, feedback_text,
            source, created_at, customer_segment, product_area,
            rating, original_category
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            record.external_id,
            content_hash,
            record.feedback_text,
            record.source,
            record.created_at.isoformat() if record.created_at else None,
            record.customer_segment,
            record.product_area,
            record.rating,
            record.original_category,
        ),
    )
    return cursor.lastrowid


def count_repeated_content(df: pd.DataFrame) -> int:
    """
    Count rows that have duplicate feedback content (after normalization).

    Args:
        df: DataFrame with Ticket Subject, Ticket Description, Product Purchased.

    Returns:
        Number of rows that share normalized content with at least one other row.
    """
    normalized_texts = []
    for _, row in df.iterrows():
        subject = row.get("Ticket Subject", "")
        description = row.get("Ticket Description", "")
        product = row.get("Product Purchased", "")
        text = construct_feedback_text(subject, description, product)
        normalized = normalize_feedback_text(text)
        normalized_texts.append(normalized)

    # Count occurrences
    from collections import Counter
    counts = Counter(normalized_texts)

    # Sum rows that have count > 1
    repeated = sum(count for count in counts.values() if count > 1)
    return repeated


def generate_preview(df: pd.DataFrame, product_id: int, db_path: Optional[Path] = None) -> PreviewResult:
    """
    Generate a preview result for the CSV data.

    Args:
        df: DataFrame with CSV data.
        product_id: Active product ID.
        db_path: Optional custom database path.

    Returns:
        PreviewResult with mapping, samples, and quality info.
    """
    # Validate schema
    is_valid, issues = validate_csv_schema(df)

    # Check for duplicate imports
    duplicate_imports = 0
    if "Ticket ID" in df.columns:
        with get_connection(db_path) as conn:
            for tid in df["Ticket ID"].dropna().unique():
                ext_id = namespace_external_id(tid)
                if check_duplicate_import(conn, product_id, ext_id):
                    duplicate_imports += 1

    # Validation summary
    valid_count = 0
    rejected_count = 0
    rejection_reasons = {}

    for _, row in df.iterrows():
        feedback, error = map_row_to_feedback(row, product_id)
        if feedback:
            valid_count += 1
        else:
            rejected_count += 1
            reason = error or "Unknown error"
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    # Sample records (first 10 valid)
    sample_records = []
    for _, row in df.iterrows():
        feedback, error = map_row_to_feedback(row, product_id)
        if feedback and len(sample_records) < 10:
            sample_records.append({
                "external_id": feedback.feedback_id,
                "feedback_text": feedback.feedback_text[:200] + ("..." if len(feedback.feedback_text) > 200 else ""),
                "source": feedback.source,
                "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
                "rating": feedback.rating,
                "original_category": feedback.original_category,
            })

    # Data quality
    total_rows = len(df)
    missing_feedback = df["Ticket Description"].isna().sum() + df["Ticket Subject"].isna().sum()
    missing_external_id = df["Ticket ID"].isna().sum()
    missing_rating = df["Customer Satisfaction Rating"].isna().sum()
    missing_timestamp = df["First Response Time"].isna().sum()

    # Rating fractional check
    fractional_ratings = 0
    for val in df["Customer Satisfaction Rating"].dropna():
        if isinstance(val, float) and not val.is_integer():
            fractional_ratings += 1

    data_quality = {
        "total_rows": total_rows,
        "missing_feedback_fields": int(missing_feedback),
        "missing_external_id": int(missing_external_id),
        "missing_rating": int(missing_rating),
        "fractional_ratings": fractional_ratings,
        "missing_timestamp": int(missing_timestamp),
        "duplicate_imports": duplicate_imports,
    }

    validation_summary = {
        "valid": valid_count,
        "rejected": rejected_count,
        "rejection_reasons": rejection_reasons,
        "duplicate_imports": duplicate_imports,
    }

    repeated_content = count_repeated_content(df)

    pii_excluded = ["Customer Name", "Customer Email", "Customer Age", "Customer Gender"]

    return PreviewResult(
        total_rows=total_rows,
        columns=list(df.columns),
        column_mapping=KAGGLE_COLUMN_MAP,
        sample_records=sample_records,
        data_quality=data_quality,
        validation_summary=validation_summary,
        repeated_content_count=repeated_content,
        pii_excluded=pii_excluded,
        timestamp_policy_note=(
            "First Response Time is used as a proxy for ticket creation time. "
            "It is not independently verified. {pct:.1f}% of values are missing. "
            "Date of Purchase and Time to Resolution are NOT used as feedback timestamps."
        ).format(pct=missing_timestamp * 100 / total_rows if total_rows else 0),
        dataset_recognized=is_valid,
    )


class CSVIngestion:
    """
    Handles CSV ingestion for ProductSignal.

    Provides preview, validation, and import functionality for
    the supported Kaggle customer support tickets dataset.
    """

    def __init__(self, product_id: int, db_path: Optional[Path] = None):
        """
        Initialize ingestion for a specific product.

        Args:
            product_id: Active ProductSignal product ID.
            db_path: Optional custom database path.
        """
        self.product_id = product_id
        self.db_path = db_path

    def load_and_validate(self, file_path: Path | str) -> tuple[pd.DataFrame, list[str]]:
        """
        Load CSV and validate schema.

        Args:
            file_path: Path to CSV file.

        Returns:
            Tuple of (DataFrame, list of validation issues).
        """
        df = load_csv(file_path)
        is_valid, issues = validate_csv_schema(df)
        return df, issues

    def preview(self, file_path: Path | str) -> PreviewResult:
        """
        Generate a preview of the CSV import.

        Does not write to database.

        Args:
            file_path: Path to CSV file.

        Returns:
            PreviewResult with mapping, samples, and quality info.
        """
        df = load_csv(file_path)
        return generate_preview(df, self.product_id, self.db_path)

    def import_csv(self, file_path: Path | str) -> IngestionResult:
        """
        Import CSV data into the database.

        Uses a transaction - all or nothing.

        Args:
            file_path: Path to CSV file.

        Returns:
            IngestionResult with counts and any errors.
        """
        df = load_csv(file_path)
        return self.import_df(df)

    def import_df(self, df: pd.DataFrame) -> IngestionResult:
        """
        Import DataFrame data into the database.

        Uses a transaction - all or nothing.

        Args:
            df: DataFrame with CSV data.

        Returns:
            IngestionResult with counts and any errors.
        """
        result = IngestionResult()
        result.total_rows = len(df)

        with get_connection(self.db_path) as conn:
            try:
                for idx, row in df.iterrows():
                    feedback, error = map_row_to_feedback(row, self.product_id)

                    if error:
                        result.rejected += 1
                        result.errors.append({
                            "row_index": int(idx),
                            "external_id": namespace_external_id(row.get("Ticket ID", "unknown")),
                            "reason": error,
                        })
                        continue

                    # Check for duplicate import
                    if check_duplicate_import(conn, self.product_id, feedback.feedback_id):
                        result.duplicate_imports += 1
                        result.warnings.append(
                            f"Skipped duplicate import: {feedback.feedback_id} (row {idx})"
                        )
                        continue

                    # Compute content hash
                    content_hash = compute_content_hash(feedback.feedback_text)

                    try:
                        insert_feedback_record(conn, feedback, self.product_id, content_hash)
                        result.imported += 1
                    except sqlite3.IntegrityError as e:
                        # Check if it's a duplicate key error (unique constraint on external_id)
                        if "UNIQUE constraint failed" in str(e) and "external_id" in str(e):
                            result.duplicate_imports += 1
                            result.warnings.append(
                                f"Duplicate import caught at DB level: {feedback.feedback_id} (row {idx})"
                            )
                        else:
                            # Unexpected integrity error - propagate to outer handler to rollback
                            raise
                    except Exception as e:
                        # Any other unexpected database error - propagate to outer handler to rollback
                        raise

                conn.commit()

            except Exception as e:
                conn.rollback()
                result.errors.append({
                    "row_index": -1,
                    "external_id": "N/A",
                    "reason": f"Transaction failed: {e}",
                })
                # Mark all as rejected on transaction failure (no partial imports)
                result.rejected = result.total_rows
                result.imported = 0

        return result


