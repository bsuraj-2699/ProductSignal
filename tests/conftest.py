"""
Pytest configuration and fixtures for ProductSignal tests.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add src to path - anchored to project root, not CWD
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="function")
def clean_db():
    """Provide a clean database for each test - creates a fresh temp database."""
    import tempfile
    from productsignal.db.connection import initialize_database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # Initialize schema
        initialize_database(db_path)
        yield db_path
    finally:
        # Cleanup
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def sample_saas_vibe():
    """Load the SaaS vibe configuration for testing."""
    from productsignal.config import load_vibe_config
    return load_vibe_config("saas")


@pytest.fixture
def sample_feedback_data():
    """Sample feedback data for testing."""
    return {
        "feedback_id": "EXT-123",
        "feedback_text": "The dashboard takes forever to load when I have more than 50 projects.",
        "source": "support_ticket",
        "created_at": "2024-01-15T10:30:00",
        "customer_segment": "enterprise",
        "product_area": "dashboard",
        "rating": 2,
        "original_category": "performance",
    }


@pytest.fixture
def sample_product_context():
    """Sample product context for testing."""
    from productsignal.product_context.repository import ProductContextCreate
    return ProductContextCreate(
        name="TestSaaS",
        product_type="service_based",
        category="saas",
        target_customers="SMBs",
        primary_use_case="Project management",
        key_features=["tasks", "reporting", "integrations"],
        description="Test SaaS product",
        vibe_key="saas",
    )