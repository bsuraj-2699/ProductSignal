"""
Feedback Ingestion Page for ProductSignal.

Allows users to upload/select CSV, preview mapping, and import feedback.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(src_path))

from productsignal.db.connection import check_database_health
from productsignal.ingestion.csv_ingestion import (
    CSVIngestion,
    generate_preview,
    load_csv,
    validate_csv_schema,
)
from productsignal._paths import get_supported_dataset_path

st.set_page_config(
    page_title="Feedback Ingestion - ProductSignal",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_sidebar():
    """Render sidebar with navigation and status."""
    with st.sidebar:
        st.title("📊 ProductSignal")
        st.caption("Customer Feedback Intelligence Platform")

        st.divider()

        # Database status
        health = check_database_health()
        if health["status"] == "healthy":
            st.success(f"🟢 Database: Connected ({health['table_count']} tables)")
        else:
            st.error(f"🔴 Database: {health['status']}")

        st.divider()

        # Active product
        if "active_product" in st.session_state and st.session_state.active_product:
            product = st.session_state.active_product
            st.info(f"**Active Project:** {product.name}")
            st.caption(f"Type: {product.product_type} → {product.category}")
            st.caption(f"Vibe: {product.vibe_key}")

            if st.button("🔄 Switch Project", use_container_width=True):
                st.session_state.active_product = None
                st.rerun()
        else:
            st.warning("⚠️ No active project")
            st.caption("Create or select a project in Product Context")


def render_page_header():
    """Render page header."""
    st.title("📥 Feedback Ingestion")
    st.subheader("Import customer feedback from CSV files")

    st.markdown("""
    Upload a CSV file containing customer feedback. ProductSignal will validate the data,
    show a preview of the mapped records, and allow you to import them into the active project.
    """)


def render_dataset_info():
    """Render information about the supported dataset."""
    with st.expander("ℹ️ Supported Dataset: Kaggle Customer Support Tickets", expanded=False):
        st.markdown("""
        **Dataset:** [Kaggle Customer Support Tickets](https://www.kaggle.com/datasets/saurabhshahane/customer-support-ticket-dataset)

        **Characteristics:**
        - 8,469 synthetic support tickets for consumer electronics products
        - Ticket types: Technical issues, billing inquiries, refund requests, cancellations, product inquiries
        - Channels: Email, phone, social media, chat
        - **Synthetic data** - not genuine SaaS feedback
        - For pipeline testing only, not model evaluation

        **Schema (17 columns):**
        - Ticket ID, Customer Name, Customer Email, Customer Age, Customer Gender
        - Product Purchased, Date of Purchase
        - Ticket Type, Ticket Subject, Ticket Description
        - Ticket Status, Resolution, Ticket Priority, Ticket Channel
        - First Response Time, Time to Resolution, Customer Satisfaction Rating

        **PII Handling:** Customer Name, Email, Age, Gender are **never stored**.
        """)

        st.warning("""
        **Known Limitations:**
        - Dataset is synthetic consumer-product data, not SaaS feedback
        - First Response Time is used as a proxy for ticket creation time (not verified)
        - 33.3% of First Response Time values are missing
        - Resolution field contains nonsensical placeholder text (67.3% missing)
        - Customer Satisfaction Rating has 67.3% missing values
        - No LICENSE file found - Kaggle attribution required, redistribution rights uncertain
        """)


def check_active_product():
    """Check if there's an active product, show error if not."""
    if "active_product" not in st.session_state or not st.session_state.active_product:
        st.error("❌ No active project. Please create or select a project in Product Context first.")
        return False
    return True


class _TempCSVContext:
    """Context manager for temporary CSV file cleanup.
    
    Ensures temporary CSV files are cleaned up even if exceptions occur
    or Streamlit reruns are triggered.
    """
    def __init__(self):
        self.path = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False  # Don't suppress exceptions
    
    def set_path(self, path: Path):
        """Set the temporary file path to be cleaned up."""
        # Clean up any existing temp file first
        self.cleanup()
        self.path = path
    
    def cleanup(self):
        """Clean up the temporary file if it exists."""
        if self.path and self.path.exists():
            try:
                self.path.unlink()
            except Exception:
                pass
        self.path = None


def _get_temp_csv_context():
    """Get or create the temporary CSV context manager for this session."""
    if "temp_csv_context" not in st.session_state:
        st.session_state.temp_csv_context = _TempCSVContext()
    return st.session_state.temp_csv_context


def render_file_selection():
    """Render file selection/upload section."""
    st.header("1️⃣ Select CSV File")

    # Clean up any previous temporary file before starting fresh
    _get_temp_csv_context().cleanup()

    # Check for default dataset
    default_path = get_supported_dataset_path()

    col1, col2 = st.columns([2, 1])

    with col1:
        if default_path and default_path.exists():
            st.info(f"📁 Found default dataset: `{default_path}`")
            use_default = st.checkbox("Use default Kaggle dataset", value=True)
            if use_default:
                return default_path

        uploaded_file = st.file_uploader(
            "Or upload a CSV file",
            type=["csv"],
            help="Upload a CSV file with the expected Kaggle schema"
        )

        if uploaded_file is not None:
            # Save to temporary location for processing
            import tempfile
            ctx = _get_temp_csv_context()
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = Path(tmp.name)
                ctx.set_path(tmp_path)
                return tmp_path
            except Exception:
                ctx.cleanup()
                raise

    with col2:
        if default_path and default_path.exists():
            st.markdown("**Dataset Info:**")
            st.caption(f"Size: {default_path.stat().st_size / 1024 / 1024:.2f} MB")
            st.caption("Rows: ~8,469")
            st.caption("Columns: 17")

    return None


def render_schema_validation(df):
    """Render schema validation results."""
    st.header("2️⃣ Schema Validation")

    is_valid, issues = validate_csv_schema(df)

    if is_valid:
        st.success("✅ CSV schema matches expected Kaggle format")
    else:
        st.error("❌ Schema validation failed")
        for issue in issues:
            st.error(f"  • {issue}")

    with st.expander("Column Details", expanded=False):
        col_info = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            non_null = df[col].notna().sum()
            null_pct = (1 - non_null / len(df)) * 100
            sample = df[col].dropna().iloc[0] if non_null > 0 else "N/A"
            col_info.append({
                "Column": col,
                "Type": dtype,
                "Non-Null": f"{non_null}/{len(df)}",
                "Null %": f"{null_pct:.1f}%",
                "Sample": str(sample)[:50]
            })
        st.dataframe(pd.DataFrame(col_info), use_container_width=True)

    return is_valid


def render_preview(preview, df):
    """Render import preview."""
    st.header("3️⃣ Import Preview")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Rows", preview.total_rows)
    with col2:
        st.metric("Valid", preview.validation_summary.get("valid", 0))
    with col3:
        st.metric("Rejected", preview.validation_summary.get("rejected", 0))
    with col4:
        st.metric("Duplicate Imports", preview.validation_summary.get("duplicate_imports", 0))

    # Data quality
    st.subheader("Data Quality")
    dq = preview.data_quality
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Missing Feedback", dq.get("missing_feedback_fields", 0))
    with col2:
        st.metric("Missing External ID", dq.get("missing_external_id", 0))
    with col3:
        st.metric("Missing Rating", dq.get("missing_rating", 0))
    with col4:
        st.metric("Fractional Ratings", dq.get("fractional_ratings", 0))

    # Rejection reasons
    if preview.validation_summary.get("rejection_reasons"):
        st.subheader("Rejection Reasons")
        for reason, count in preview.validation_summary["rejection_reasons"].items():
            st.caption(f"  • {reason}: {count}")

    # Repeated content
    st.metric("Repeated Content (shared hashes)", preview.repeated_content_count)
    st.caption("Rows that share normalized content with at least one other row. These are preserved.")

    # PII exclusion
    st.subheader("PII Exclusion")
    st.success("✅ The following PII columns will NOT be stored:")
    for pii in preview.pii_excluded:
        st.caption(f"  • {pii}")

    # Timestamp policy
    st.subheader("Timestamp Policy")
    st.info(preview.timestamp_policy_note)

    # Sample records
    st.subheader("Sample Mapped Records (first 10 valid)")
    if preview.sample_records:
        sample_df = pd.DataFrame(preview.sample_records)
        st.dataframe(sample_df, use_container_width=True)
    else:
        st.warning("No valid records to preview")

    # Column mapping
    with st.expander("Column Mapping", expanded=False):
        mapping_df = pd.DataFrame([
            {"ProductSignal Field": k, "CSV Column": v}
            for k, v in preview.column_mapping.items()
        ])
        st.dataframe(mapping_df, use_container_width=True)


def render_import(ingestion, df, preview):
    """Render import button and handle import."""
    st.header("4️⃣ Import")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🚀 Import Feedback", type="primary", use_container_width=True,
                     disabled=preview.validation_summary.get("valid", 0) == 0):
            with st.spinner("Importing feedback records..."):
                result = ingestion.import_df(df)

            # Display results
            has_transaction_failure = any(
                "Transaction failed" in err.get("reason", "") for err in result.errors
            )

            if has_transaction_failure:
                st.error("Import failed - transaction rolled back")
            elif result.imported > 0:
                st.success("Import completed successfully!")
            else:
                st.warning("Import completed with no records imported")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Rows", result.total_rows)
            with col2:
                st.metric("✅ Imported", result.imported)
            with col3:
                st.metric("❌ Rejected", result.rejected)
            with col4:
                st.metric("⚠️ Duplicate Imports Skipped", result.duplicate_imports)

            if result.errors:
                st.subheader("Errors")
                for err in result.errors[:20]:
                    st.error(f"Row {err['row_index']} ({err['external_id']}): {err['reason']}")
                if len(result.errors) > 20:
                    st.caption(f"... and {len(result.errors) - 20} more errors")

            if result.warnings:
                st.subheader("Warnings")
                for warn in result.warnings[:20]:
                    st.warning(warn)

            # Clean up temporary file before rerun
            _get_temp_csv_context().cleanup()
            st.rerun()

    with col2:
        st.caption("Only valid records will be imported")
        st.caption("Duplicate imports (same external_id) are skipped")

    with col3:
        if preview.validation_summary.get("rejected", 0) > 0:
            st.warning(f"{preview.validation_summary['rejected']} records will be rejected")


def main():
    """Main page entry point."""
    # Initialize session state
    if "db_initialized" not in st.session_state:
        st.session_state.db_initialized = False
    if "active_product" not in st.session_state:
        st.session_state.active_product = None

    # Initialize database
    if not st.session_state.db_initialized:
        try:
            from productsignal.db.connection import initialize_database
            initialize_database()
            st.session_state.db_initialized = True
        except Exception as e:
            st.error(f"❌ Database initialization failed: {e}")
            st.stop()

    render_sidebar()

    # Check active product
    if not check_active_product():
        _get_temp_csv_context().cleanup()
        return

    render_page_header()
    render_dataset_info()

    # File selection
    file_path = render_file_selection()

    if file_path is None:
        st.info("👆 Please select or upload a CSV file to begin")
        _get_temp_csv_context().cleanup()
        return

    # Track temporary file lifecycle; the bundled Kaggle source CSV is never deleted
    default_path = get_supported_dataset_path()
    ctx = _get_temp_csv_context()
    is_temp = default_path is None or not file_path.samefile(default_path)
    if is_temp:
        ctx.set_path(file_path)
    else:
        ctx.cleanup()

    try:
        # Load CSV (friendly error instead of a raw traceback)
        try:
            df = load_csv(file_path)
        except Exception as e:
            st.error(f"❌ Failed to load CSV: {e}")
            return
        st.success(f"✅ Loaded CSV: {len(df)} rows, {len(df.columns)} columns")

        # Schema validation
        if not render_schema_validation(df):
            st.error("Cannot proceed with invalid schema")
            return

        # Generate preview
        product_id = st.session_state.active_product.product_id
        ingestion = CSVIngestion(product_id)

        preview = generate_preview(df, product_id)

        # Render preview and import section (import cleans up before st.rerun)
        render_preview(preview, df)
        render_import(ingestion, df, preview)
    finally:
        # Runs on every exit path: CSV parsing errors, preview exceptions,
        # schema-validation early return, and the rerun triggered after import.
        ctx.cleanup()


if __name__ == "__main__":
    main()