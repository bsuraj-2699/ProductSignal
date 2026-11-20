"""
Tests for database initialization and operations.
"""

import pytest
from pathlib import Path

from productsignal.db.connection import (
    initialize_database,
    check_database_health,
    get_connection,
    execute_query,
    execute_write,
)


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_initialize_database_creates_tables(self, clean_db):
        """Test that initialize_database creates all expected tables."""
        health = check_database_health(clean_db)
        assert health["status"] == "healthy"
        assert health["foreign_keys_enabled"] is True
        assert health["wal_mode"] is True
        assert health["table_count"] == 10

        expected_tables = {
            "products", "feedback", "classifications", "clusters",
            "cluster_feedback", "opportunities", "opportunity_evidence",
            "briefs", "experiments", "prds"
        }
        assert set(health["tables"]) == expected_tables
        assert health["missing_tables"] == []

    def test_initialize_database_idempotent(self, clean_db):
        """Test that running initialize_database twice works."""
        # First initialization done by fixture
        health1 = check_database_health(clean_db)
        assert health1["status"] == "healthy"

        # Second initialization
        initialize_database(clean_db)
        health2 = check_database_health(clean_db)
        assert health2["status"] == "healthy"
        assert health2["table_count"] == 10

    def test_foreign_keys_enforced(self, clean_db):
        """Test that foreign key constraints are enforced."""
        with get_connection(clean_db) as conn:
            # Try to insert feedback with non-existent product_id
            with pytest.raises(Exception) as exc_info:
                conn.execute(
                    "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                    (999, "hash123", "Test feedback")
                )
                conn.commit()
            # Should raise foreign key constraint error
            assert "FOREIGN KEY constraint failed" in str(exc_info.value) or "foreign key constraint failed" in str(exc_info.value).lower()

    def test_wal_mode_enabled(self, clean_db):
        """Test that WAL mode is enabled."""
        with get_connection(clean_db) as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].lower() == "wal"


class TestDatabaseOperations:
    """Tests for database query execution helpers."""

    def test_execute_query_select(self, clean_db):
        """Test execute_query for SELECT statements."""
        # Insert a product first
        execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product", "service_based", "saas", "saas"),
            clean_db
        )

        # Query it back
        results = execute_query(
            "SELECT * FROM products WHERE name = ?",
            ("Test Product",),
            clean_db,
            fetch="all"
        )
        assert len(results) == 1
        assert results[0]["name"] == "Test Product"

    def test_execute_query_fetch_one(self, clean_db):
        """Test execute_query with fetch='one'."""
        execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product", "service_based", "saas", "saas"),
            clean_db
        )

        result = execute_query(
            "SELECT * FROM products WHERE name = ?",
            ("Test Product",),
            clean_db,
            fetch="one"
        )
        assert result is not None
        assert result["name"] == "Test Product"

    def test_execute_write_returns_lastrowid(self, clean_db):
        """Test execute_write returns lastrowid."""
        rowid = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product", "service_based", "saas", "saas"),
            clean_db
        )
        assert rowid > 0

        rowid2 = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product 2", "service_based", "saas", "saas"),
            clean_db
        )
        assert rowid2 > rowid

    def test_execute_write_commits(self, clean_db):
        """Test that execute_write commits the transaction."""
        execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product", "service_based", "saas", "saas"),
            clean_db
        )

        # Query in a new connection should see the data
        with get_connection(clean_db) as conn:
            result = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()
            assert result["count"] == 1


class TestDatabaseSchema:
    """Tests for specific schema constraints."""

    def test_products_table_constraints(self, clean_db):
        """Test products table constraints."""
        # Valid insert
        execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Valid Product", "service_based", "saas", "saas"),
            clean_db
        )

        # Invalid product_type should fail
        with get_connection(clean_db) as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                    ("Invalid", "invalid_type", "saas", "saas")
                )
                conn.commit()

    def test_feedback_table_constraints(self, clean_db):
        """Test feedback table constraints."""
        # Create product first
        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        # Valid feedback
        execute_write(
            "INSERT INTO feedback (product_id, content_hash, feedback_text, rating) VALUES (?, ?, ?, ?)",
            (product_id, "hash123", "Great product!", 5),
            clean_db
        )

        # Invalid rating should fail
        with get_connection(clean_db) as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO feedback (product_id, content_hash, feedback_text, rating) VALUES (?, ?, ?, ?)",
                    (product_id, "hash456", "Bad rating", 10)
                )
                conn.commit()

    def test_classifications_table_constraints(self, clean_db):
        """Test classifications table constraints."""
        # Setup
        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )
        feedback_id = execute_write(
            "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
            (product_id, "hash123", "Test feedback"),
            clean_db
        )

        # Valid classification
        execute_write(
            """INSERT INTO classifications
               (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (feedback_id, product_id, "feature_request", "positive", "low", "Customer wants feature", 0.9),
            clean_db
        )

        # Invalid sentiment should fail
        with get_connection(clean_db) as conn:
            with pytest.raises(Exception):
                conn.execute(
                    """INSERT INTO classifications
                       (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (feedback_id, product_id, "feature_request", "invalid_sentiment", "low", "Test", 0.9)
                )
                conn.commit()

        # Invalid confidence should fail
        with get_connection(clean_db) as conn:
            with pytest.raises(Exception):
                conn.execute(
                    """INSERT INTO classifications
                       (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (feedback_id, product_id, "feature_request", "positive", "low", "Test", 1.5)
                )
                conn.commit()

    def test_cascade_delete_products(self, clean_db):
        """Test that deleting a product cascades to related data."""
        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )
        feedback_id = execute_write(
            "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
            (product_id, "hash123", "Test feedback"),
            clean_db
        )
        execute_write(
            """INSERT INTO classifications
               (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (feedback_id, product_id, "feature_request", "positive", "low", "Test", 0.9),
            clean_db
        )

        # Delete product
        with get_connection(clean_db) as conn:
            conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
            conn.commit()

        # Feedback and classifications should be deleted
        with get_connection(clean_db) as conn:
            feedback_count = conn.execute("SELECT COUNT(*) as count FROM feedback WHERE product_id = ?", (product_id,)).fetchone()
            class_count = conn.execute("SELECT COUNT(*) as count FROM classifications WHERE product_id = ?", (product_id,)).fetchone()
            assert feedback_count["count"] == 0
            assert class_count["count"] == 0