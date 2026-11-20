"""
ProductSignal - Main Streamlit Application Entry Point.

AI-Powered Customer Feedback Intelligence & Product Discovery Platform.
"""

import streamlit as st
from pathlib import Path
import sys

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_path))

from productsignal.db.connection import initialize_database, check_database_health
from productsignal.product_context.repository import get_repository, ProductContextCreate
from productsignal.config import list_available_vibes, load_vibe_config


# Page configuration
st.set_page_config(
    page_title="ProductSignal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state():
    """Initialize Streamlit session state."""
    if "db_initialized" not in st.session_state:
        st.session_state.db_initialized = False
    if "active_product" not in st.session_state:
        st.session_state.active_product = None
    if "repo" not in st.session_state:
        st.session_state.repo = None


def initialize_database_once():
    """Initialize database on first run."""
    if not st.session_state.db_initialized:
        try:
            initialize_database()
            st.session_state.db_initialized = True
            st.session_state.repo = get_repository()
            st.success("✅ Database initialized successfully")
        except Exception as e:
            st.error(f"❌ Database initialization failed: {e}")
            st.stop()


def render_sidebar():
    """Render the sidebar with navigation and status."""
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
        if st.session_state.active_product:
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

        st.divider()

        # Quick stats
        if st.session_state.active_product and st.session_state.repo:
            try:
                from productsignal.db.connection import execute_query
                product_id = st.session_state.active_product.product_id

                feedback_count = execute_query(
                    "SELECT COUNT(*) as count FROM feedback WHERE product_id = ?",
                    (product_id,), fetch="one"
                )["count"]

                cluster_count = execute_query(
                    "SELECT COUNT(*) as count FROM clusters WHERE product_id = ?",
                    (product_id,), fetch="one"
                )["count"]

                opportunity_count = execute_query(
                    "SELECT COUNT(*) as count FROM opportunities WHERE product_id = ?",
                    (product_id,), fetch="one"
                )["count"]

                st.metric("Feedback Records", feedback_count)
                st.metric("Problem Clusters", cluster_count)
                st.metric("Opportunities", opportunity_count)
            except Exception:
                pass


def render_home_page():
    """Render the main home page."""
    st.title("📊 ProductSignal")
    st.subheader("AI-Powered Customer Feedback Intelligence & Product Discovery")

    st.markdown("""
    Transform unstructured customer feedback into structured product insights.
    Move from thousands of customer comments to a prioritized, evidence-backed product roadmap.
    """)

    st.divider()

    # Current project status
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("🎯 Current Project Status")

        if st.session_state.active_product:
            product = st.session_state.active_product
            st.success(f"**Active:** {product.name} ({product.product_type} → {product.category})")

            with st.expander("📋 Project Details", expanded=True):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f"**Target Customers:** {product.target_customers or 'Not specified'}")
                    st.write(f"**Primary Use Case:** {product.primary_use_case or 'Not specified'}")
                with col_b:
                    st.write(f"**Key Features:** {', '.join(product.key_features) if product.key_features else 'Not specified'}")
                    st.write(f"**Product Vibe:** {product.vibe_key}")

                if product.description:
                    st.write(f"**Description:** {product.description}")
        else:
            st.warning("**No active project** — Create a project in **Product Context** to begin.")

    with col2:
        st.header("🔧 Quick Actions")

        if not st.session_state.active_product:
            # Product Context creation is rendered inline below
            pass
        else:
            st.button("📥 Upload Feedback", disabled=True, use_container_width=True, help="Phase 2: CSV Ingestion")
            st.button("🔍 Explore Problems", disabled=True, use_container_width=True, help="Phase 2: Problem Clustering")
            st.button("📈 View Opportunities", disabled=True, use_container_width=True, help="Phase 2: Opportunity Scoring")

    st.divider()

    # Workflow overview
    st.header("🔄 ProductSignal Workflow")

    workflow_steps = [
        ("1️⃣ Product Context", "Define your product, target customers, and use case"),
        ("2️⃣ Feedback Ingestion", "Upload customer feedback from CSV files"),
        ("3️⃣ AI Classification", "Classify feedback using SaaS Product Vibe"),
        ("4️⃣ Problem Clustering", "Group similar feedback into problem clusters"),
        ("5️⃣ Opportunity Scoring", "Rank problems by frequency, severity, and impact"),
        ("6️⃣ Opportunity Brief", "Generate evidence-backed opportunity briefs"),
        ("7️⃣ Experiment & PRD", "Create testable hypotheses and draft PRDs"),
    ]

    cols = st.columns(len(workflow_steps))
    for i, (step, desc) in enumerate(workflow_steps):
        with cols[i]:
            st.markdown(f"**{step}**")
            st.caption(desc)

    st.divider()

    # Product Vibe info
    st.header("🎨 Active Product Vibe: SaaS")

    try:
        vibe = load_vibe_config("saas")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("🎯 Analytical Focus")
            for focus in vibe.analytical_focus:
                st.write(f"• {focus.replace('_', ' ').title()}")

        with col2:
            st.subheader("📂 Classification Categories")
            for cat in vibe.get_primary_categories():
                desc = vibe.get_category_description(cat)
                st.write(f"• **{cat.replace('_', ' ').title()}**")
                if desc:
                    st.caption(desc)

        with col3:
            st.subheader("⚖️ Scoring Weights")
            weights = vibe.scoring_weights
            st.write(f"• Frequency: {weights.frequency:.0%}")
            st.write(f"• Severity: {weights.severity:.0%}")
            st.write(f"• Segment Impact: {weights.segment_impact:.0%}")
            st.write(f"• Recency: {weights.recency:.0%}")
            st.write(f"• Business Relevance: {weights.business_relevance:.0%}")

    except Exception as e:
        st.error(f"Failed to load SaaS vibe configuration: {e}")


def render_product_context_setup():
    """Render product context creation form (inline for initial setup)."""
    st.header("🎯 Product Context Setup")

    st.markdown("""
    Before analyzing feedback, define your product context. This activates the appropriate
    **Product Vibe** — the analytical lens that shapes how ProductSignal interprets your feedback.
    """)

    with st.form("create_product_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Product Name *", placeholder="e.g., FlowDesk")
            product_type = st.selectbox(
                "Product Type *",
                ["service_based", "consumer_facing"],
                help="Service-based: SaaS, enterprise software. Consumer-facing: mobile apps, e-commerce."
            )
            category = st.text_input("Category *", placeholder="e.g., SaaS — Project Management")

        with col2:
            target_customers = st.text_area("Target Customers *", placeholder="e.g., Small and medium businesses")
            primary_use_case = st.text_area("Primary Use Case *", placeholder="e.g., Project collaboration and task management")
            vibe_key = st.selectbox("Product Vibe *", list_available_vibes())

        key_features = st.text_area(
            "Key Features (one per line)",
            placeholder="Task assignment\nReporting\nAutomation\nIntegrations"
        )
        description = st.text_area("Description (optional)", placeholder="Additional product context...")

        submitted = st.form_submit_button("💾 Create Project", type="primary", use_container_width=True)

        if submitted:
            # Validation
            errors = []
            if not name.strip():
                errors.append("Product name is required")
            if not category.strip():
                errors.append("Category is required")
            if not target_customers.strip():
                errors.append("Target customers is required")
            if not primary_use_case.strip():
                errors.append("Primary use case is required")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    create = ProductContextCreate(
                        name=name.strip(),
                        product_type=product_type,
                        category=category.strip(),
                        target_customers=target_customers.strip(),
                        primary_use_case=primary_use_case.strip(),
                        key_features=[f.strip() for f in key_features.split("\n") if f.strip()] if key_features else [],
                        description=description.strip() if description else None,
                        vibe_key=vibe_key,
                    )

                    repo = st.session_state.repo
                    product = repo.create_product(create)
                    repo.set_active_product(product.product_id)

                    st.session_state.active_product = product
                    st.success(f"✅ Project '{product.name}' created and activated!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to create project: {e}")


def main():
    """Main application entry point."""
    init_session_state()
    initialize_database_once()
    render_sidebar()

    # Route based on active product
    if not st.session_state.active_product:
        # Check if any products exist
        repo = st.session_state.repo
        products = repo.list_products()

        if products:
            st.header("📁 Select a Project")
            product_names = {p.product_id: f"{p.name} ({p.product_type} → {p.category})" for p in products}
            selected_id = st.selectbox(
                "Choose a project to activate:",
                options=list(product_names.keys()),
                format_func=lambda x: product_names[x],
            )

            if st.button("▶️ Activate Project", type="primary"):
                product = repo.set_active_product(selected_id)
                if product:
                    st.session_state.active_product = product
                    st.rerun()
        else:
            render_product_context_setup()
    else:
        render_home_page()


if __name__ == "__main__":
    main()