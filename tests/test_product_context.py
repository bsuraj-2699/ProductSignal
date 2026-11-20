"""
Tests for Product Context Repository.
"""

import pytest
from productsignal.product_context.repository import (
    ProductContextRepository,
    ProductContextCreate,
    ProductContextUpdate,
)
from productsignal.config import load_vibe_config


class TestProductContextRepository:
    """Tests for ProductContextRepository CRUD operations."""

    def test_create_product(self, clean_db):
        """Test creating a product context."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="TestSaaS",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Project management",
            key_features=["tasks", "reporting"],
            description="Test product",
            vibe_key="saas",
        )

        product = repo.create_product(create)

        assert product.product_id > 0  # Auto-increment ID
        assert product.name == "TestSaaS"
        assert product.product_type == "service_based"
        assert product.category == "saas"
        assert product.target_customers == "SMBs"
        assert product.primary_use_case == "Project management"
        assert product.key_features == ["tasks", "reporting"]
        assert product.description == "Test product"
        assert product.vibe_key == "saas"
        assert product.vibe is not None
        assert product.vibe.product_category == "saas"

    def test_create_product_invalid_vibe_key(self, clean_db):
        """Test that invalid vibe_key raises error."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="Test",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Test",
            vibe_key="nonexistent_vibe",
        )

        with pytest.raises(FileNotFoundError):
            repo.create_product(create)

    def test_get_product(self, clean_db):
        """Test getting a product by ID."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="TestSaaS",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Project management",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        product = repo.get_product(created.product_id)
        assert product is not None
        assert product.product_id == created.product_id
        assert product.name == "TestSaaS"

    def test_get_product_not_found(self, clean_db):
        """Test getting non-existent product returns None."""
        repo = ProductContextRepository(clean_db)
        product = repo.get_product(999)
        assert product is None

    def test_get_product_by_name(self, clean_db):
        """Test getting a product by name."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="UniqueProductName",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Project management",
            vibe_key="saas",
        )
        repo.create_product(create)

        product = repo.get_product_by_name("UniqueProductName")
        assert product is not None
        assert product.name == "UniqueProductName"

        # Non-existent name
        assert repo.get_product_by_name("NonExistent") is None

    def test_list_products(self, clean_db):
        """Test listing all products."""
        repo = ProductContextRepository(clean_db)

        # Initially empty
        products = repo.list_products()
        assert len(products) == 0

        # Create multiple products
        for i in range(3):
            create = ProductContextCreate(
                name=f"Product{i}",
                product_type="service_based",
                category="saas",
                target_customers="SMBs",
                primary_use_case="Test",
                vibe_key="saas",
            )
            repo.create_product(create)

        products = repo.list_products()
        assert len(products) == 3
        # Should be ordered by created_at DESC (newest first)
        assert products[0].name == "Product2"
        assert products[1].name == "Product1"
        assert products[2].name == "Product0"

    def test_update_product(self, clean_db):
        """Test updating a product."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="OriginalName",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Original use case",
            key_features=["feature1"],
            description="Original description",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        # Update
        update = ProductContextUpdate(
            name="UpdatedName",
            target_customers="Enterprise",
            key_features=["feature1", "feature2", "feature3"],
            description="Updated description",
        )
        updated = repo.update_product(created.product_id, update)

        assert updated is not None
        assert updated.name == "UpdatedName"
        assert updated.target_customers == "Enterprise"
        assert updated.key_features == ["feature1", "feature2", "feature3"]
        assert updated.description == "Updated description"
        # Unchanged fields preserved
        assert updated.product_type == "service_based"
        assert updated.category == "saas"
        assert updated.primary_use_case == "Original use case"

    def test_update_product_not_found(self, clean_db):
        """Test updating non-existent product returns None."""
        repo = ProductContextRepository(clean_db)
        update = ProductContextUpdate(name="NewName")
        result = repo.update_product(999, update)
        assert result is None

    def test_update_product_invalid_vibe_key(self, clean_db):
        """Test updating with invalid vibe_key raises error."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="Test",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Test",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        update = ProductContextUpdate(vibe_key="nonexistent")
        with pytest.raises(FileNotFoundError):
            repo.update_product(created.product_id, update)

    def test_update_product_no_changes(self, clean_db):
        """Test updating with no changes returns existing product."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="Test",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Test",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        update = ProductContextUpdate()  # No fields set
        result = repo.update_product(created.product_id, update)
        assert result is not None
        assert result.product_id == created.product_id

    def test_delete_product(self, clean_db):
        """Test deleting a product cascades."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="ToDelete",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Test",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        # Delete
        result = repo.delete_product(created.product_id)
        assert result is True

        # Product should be gone
        assert repo.get_product(created.product_id) is None

    def test_delete_product_not_found(self, clean_db):
        """Test deleting non-existent product returns False."""
        repo = ProductContextRepository(clean_db)
        result = repo.delete_product(999)
        assert result is False

    def test_set_active_product(self, clean_db):
        """Test setting active product loads vibe."""
        repo = ProductContextRepository(clean_db)
        create = ProductContextCreate(
            name="TestSaaS",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Project management",
            vibe_key="saas",
        )
        created = repo.create_product(create)

        active = repo.set_active_product(created.product_id)
        assert active is not None
        assert active.product_id == created.product_id
        assert active.vibe is not None

        # Check global active vibe is set
        from productsignal.config import get_active_vibe
        assert get_active_vibe() is not None
        assert get_active_vibe().product_category == "saas"

    def test_set_active_product_not_found(self, clean_db):
        """Test setting active product with invalid ID returns None."""
        repo = ProductContextRepository(clean_db)
        result = repo.set_active_product(999)
        assert result is None

    def test_multiple_products_supported(self, clean_db):
        """Test that database supports multiple products (MVP uses one active)."""
        repo = ProductContextRepository(clean_db)

        # Create multiple products
        for i in range(3):
            create = ProductContextCreate(
                name=f"Product{i}",
                product_type="service_based",
                category="saas",
                target_customers="SMBs",
                primary_use_case="Test",
                vibe_key="saas",
            )
            repo.create_product(create)

        products = repo.list_products()
        assert len(products) == 3

        # Each has its own vibe loaded
        for product in products:
            assert product.vibe is not None
            assert product.vibe.product_category == "saas"


class TestRepeatedFeedbackPreservation:
    """Tests that repeated feedback is preserved (not deduplicated)."""

    def test_repeated_feedback_preserved(self, clean_db):
        """Test that feedback with same content_hash can be inserted multiple times."""
        from productsignal.db.connection import execute_write, execute_query

        # Setup product
        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        # Insert same feedback text twice (different external_ids)
        feedback_text = "The dashboard is slow"
        content_hash = "same_hash_for_same_text"  # In reality computed from text

        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-1", content_hash, feedback_text),
            clean_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-2", content_hash, feedback_text),
            clean_db
        )

        # Both should exist
        results = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id,),
            clean_db,
            fetch="all"
        )
        assert len(results) == 2
        assert results[0]["external_id"] == "EXT-1"
        assert results[1]["external_id"] == "EXT-2"
        assert results[0]["feedback_text"] == feedback_text
        assert results[1]["feedback_text"] == feedback_text

    def test_external_id_prevents_reimport(self, clean_db):
        """Test that external_id can be used to prevent re-imports."""
        from productsignal.db.connection import execute_write, execute_query

        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        # First import
        feedback_id = execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "ZENDESK-123", "hash1", "Feedback from Zendesk"),
            clean_db
        )

        # Check if external_id exists before re-importing
        existing = execute_query(
            "SELECT feedback_id FROM feedback WHERE product_id = ? AND external_id = ?",
            (product_id, "ZENDESK-123"),
            clean_db,
            fetch="one"
        )
        assert existing is not None
        assert existing["feedback_id"] == feedback_id


class TestExternalIdUniqueness:
    """Tests for external_id uniqueness constraint (F1)."""

    def test_same_product_same_external_id_rejected(self, clean_db):
        """Same product + same external ID = second insert rejected."""
        from productsignal.db.connection import execute_write, execute_query
        import sqlite3

        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        # First insert
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "ZENDESK-123", "hash1", "First feedback"),
            clean_db
        )

        # Second insert with same product_id and external_id should fail
        with pytest.raises(sqlite3.IntegrityError):
            execute_write(
                "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
                (product_id, "ZENDESK-123", "hash2", "Duplicate feedback"),
                clean_db
            )

        # Verify only one record exists
        results = execute_query(
            "SELECT * FROM feedback WHERE product_id = ? AND external_id = ?",
            (product_id, "ZENDESK-123"),
            clean_db,
            fetch="all"
        )
        assert len(results) == 1

    def test_same_product_different_external_ids_accepted(self, clean_db):
        """Same product + different external IDs = both accepted."""
        from productsignal.db.connection import execute_write, execute_query

        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-1", "hash1", "Feedback 1"),
            clean_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-2", "hash2", "Feedback 2"),
            clean_db
        )

        results = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id,),
            clean_db,
            fetch="all"
        )
        assert len(results) == 2
        external_ids = {r["external_id"] for r in results}
        assert external_ids == {"EXT-1", "EXT-2"}

    def test_same_product_null_external_ids_accepted(self, clean_db):
        """Same product + NULL external IDs = multiple records accepted."""
        from productsignal.db.connection import execute_write, execute_query

        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, None, "hash1", "Feedback 1"),
            clean_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, None, "hash2", "Feedback 2"),
            clean_db
        )

        results = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id,),
            clean_db,
            fetch="all"
        )
        assert len(results) == 2
        assert all(r["external_id"] is None for r in results)

    def test_different_products_same_external_id_accepted(self, clean_db):
        """Different products + same external ID = both accepted."""
        from productsignal.db.connection import execute_write, execute_query

        product_id_1 = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Product 1", "service_based", "saas", "saas"),
            clean_db
        )
        product_id_2 = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Product 2", "service_based", "saas", "saas"),
            clean_db
        )

        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id_1, "ZENDESK-123", "hash1", "Feedback for product 1"),
            clean_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id_2, "ZENDESK-123", "hash2", "Feedback for product 2"),
            clean_db
        )

        results_1 = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id_1,),
            clean_db,
            fetch="all"
        )
        results_2 = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id_2,),
            clean_db,
            fetch="all"
        )
        assert len(results_1) == 1
        assert len(results_2) == 1
        assert results_1[0]["external_id"] == "ZENDESK-123"
        assert results_2[0]["external_id"] == "ZENDESK-123"

    def test_identical_content_different_external_ids_preserved(self, clean_db):
        """Identical feedback content with different external IDs = both preserved."""
        from productsignal.db.connection import execute_write, execute_query

        product_id = execute_write(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test", "service_based", "saas", "saas"),
            clean_db
        )

        feedback_text = "The dashboard is slow"
        content_hash = "same_content_hash"

        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-1", content_hash, feedback_text),
            clean_db
        )
        execute_write(
            "INSERT INTO feedback (product_id, external_id, content_hash, feedback_text) VALUES (?, ?, ?, ?)",
            (product_id, "EXT-2", content_hash, feedback_text),
            clean_db
        )

        results = execute_query(
            "SELECT * FROM feedback WHERE product_id = ?",
            (product_id,),
            clean_db,
            fetch="all"
        )
        assert len(results) == 2
        assert results[0]["feedback_text"] == feedback_text
        assert results[1]["feedback_text"] == feedback_text
        assert results[0]["external_id"] != results[1]["external_id"]


class TestActiveProductSelection:
    """Tests for explicit active product selection (F3)."""

    def test_set_active_product_sets_is_active_flag(self, clean_db):
        """Setting active product should set is_active = 1 in database."""
        from productsignal.db.connection import execute_query
        repo = ProductContextRepository(clean_db)
        
        create = ProductContextCreate(
            name="TestSaaS",
            product_type="service_based",
            category="saas",
            target_customers="SMBs",
            primary_use_case="Project management",
            vibe_key="saas",
        )
        product = repo.create_product(create)
        
        # Initially not active
        row = execute_query("SELECT is_active FROM products WHERE product_id = ?", (product.product_id,), clean_db, fetch="one")
        assert row["is_active"] == 0
        
        # Set as active
        active = repo.set_active_product(product.product_id)
        assert active is not None
        
        # Verify is_active flag is set
        row = execute_query("SELECT is_active FROM products WHERE product_id = ?", (product.product_id,), clean_db, fetch="one")
        assert row["is_active"] == 1

    def test_get_active_product_returns_explicit_active(self, clean_db):
        """get_active_product should return the explicitly active product."""
        repo = ProductContextRepository(clean_db)
        
        # Create two products
        create1 = ProductContextCreate(name="Product1", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        create2 = ProductContextCreate(name="Product2", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        p1 = repo.create_product(create1)
        p2 = repo.create_product(create2)
        
        # Neither is active initially
        assert repo.get_active_product() is None
        
        # Activate second product
        repo.set_active_product(p2.product_id)
        
        # Should return the explicitly active product
        active = repo.get_active_product()
        assert active is not None
        assert active.product_id == p2.product_id
        assert active.name == "Product2"

    def test_only_one_active_product_at_a_time(self, clean_db):
        """Only one product can be active at a time."""
        repo = ProductContextRepository(clean_db)
        
        create1 = ProductContextCreate(name="Product1", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        create2 = ProductContextCreate(name="Product2", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        p1 = repo.create_product(create1)
        p2 = repo.create_product(create2)
        
        # Activate first
        repo.set_active_product(p1.product_id)
        assert repo.get_active_product().product_id == p1.product_id
        
        # Activate second - should deactivate first
        repo.set_active_product(p2.product_id)
        assert repo.get_active_product().product_id == p2.product_id
        
        # Verify first is no longer active
        from productsignal.db.connection import execute_query
        row1 = execute_query("SELECT is_active FROM products WHERE product_id = ?", (p1.product_id,), clean_db, fetch="one")
        row2 = execute_query("SELECT is_active FROM products WHERE product_id = ?", (p2.product_id,), clean_db, fetch="one")
        assert row1["is_active"] == 0
        assert row2["is_active"] == 1

    def test_get_active_product_handles_missing_active_product(self, clean_db):
        """get_active_product returns None when no active product exists."""
        repo = ProductContextRepository(clean_db)
        
        create = ProductContextCreate(name="Test", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        repo.create_product(create)
        
        # No product activated
        assert repo.get_active_product() is None

    def test_set_active_product_nonexistent_returns_none(self, clean_db):
        """Setting active product with invalid ID returns None."""
        repo = ProductContextRepository(clean_db)
        
        result = repo.set_active_product(999)
        assert result is None
        assert repo.get_active_product() is None

    def test_deleted_active_product_handled(self, clean_db):
        """If active product is deleted, get_active_product returns None."""
        repo = ProductContextRepository(clean_db)
        
        create = ProductContextCreate(name="Test", product_type="service_based", category="saas",
                                       target_customers="SMBs", primary_use_case="Test", vibe_key="saas")
        product = repo.create_product(create)
        
        repo.set_active_product(product.product_id)
        assert repo.get_active_product() is not None
        
        # Delete the active product
        repo.delete_product(product.product_id)
        
        # Should return None (no active product)
        assert repo.get_active_product() is None