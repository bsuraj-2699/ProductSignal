"""
CSV Ingestion module for ProductSignal.

Provides dataset-specific CSV loading, validation, and import functionality.
"""

from .csv_ingestion import (
    CSVIngestion,
    IngestionResult,
    PreviewResult,
    load_csv,
    validate_csv_schema,
    map_row_to_feedback,
    construct_feedback_text,
    replace_placeholder,
    namespace_external_id,
    parse_timestamp,
    validate_rating,
    construct_original_category,
)

__all__ = [
    "CSVIngestion",
    "IngestionResult",
    "PreviewResult",
    "load_csv",
    "validate_csv_schema",
    "map_row_to_feedback",
    "construct_feedback_text",
    "replace_placeholder",
    "namespace_external_id",
    "parse_timestamp",
    "validate_rating",
    "construct_original_category",
]