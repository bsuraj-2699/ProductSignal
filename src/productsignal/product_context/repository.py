"""
Product context repository for ProductSignal.

Provides CRUD operations for product configurations.
"""

import json
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass
from pathlib import Path

from ..db.connection import get_connection, execute_query, execute_write
from ..config import load_vibe_config, ProductVibe, set_active_vibe, get_active_vibe


@dataclass
class ProductContextCreate:
    """Data for creating a new product context."""

    name: str
    product_type: str
    category: str
    target_customers: Optional[str] = None
    primary_use_case: Optional[str] = None
    key_features: Optional[List[str]] = None
    description: Optional[str] = None
    vibe_key: str = "saas"


@dataclass
class ProductContextUpdate:
    """Data for updating an existing product context."""

    name: Optional[str] = None
    product_type: Optional[str] = None
    category: Optional[str] = None
    target_customers: Optional[str] = None
    primary_use_case: Optional[str] = None
    key_features: Optional[List[str]] = None
    description: Optional[str] = None
    vibe_key: Optional[str] = None


@dataclass
class ProductContext:
    """Product context with loaded vibe configuration."""

    product_id: int
    name: str
    product_type: str
    category: str
    target_customers: Optional[str]
    primary_use_case: Optional[str]
    key_features: List[str]
    description: Optional[str]
    vibe_key: str
    created_at: datetime
    updated_at: datetime
    vibe: Optional[ProductVibe] = None

    @property
    def is_saas(self) -> bool:
        """Check if this is a SaaS product."""
        return self.product_type == "service_based" and self.category == "saas"


class ProductContextRepository:
    """Repository for product context CRUD operations."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def create_product(self, create: ProductContextCreate) -> ProductContext:
        """
        Create a new product context.

        Args:
            create: Product creation data

        Returns:
            Created ProductContext with loaded vibe

        Raises:
            ValueError: If vibe_key is invalid or product creation fails
        """
        # Validate vibe_key by loading the vibe
        vibe = load_vibe_config(create.vibe_key)

        key_features_json = json.dumps(create.key_features or [])

        query = """
            INSERT INTO products (name, product_type, category, target_customers,
                                  primary_use_case, key_features, description, vibe_key, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            create.name,
            create.product_type,
            create.category,
            create.target_customers,
            create.primary_use_case,
            key_features_json,
            create.description,
            create.vibe_key,
            False,  # is_active - explicitly set to False on creation
        )

        product_id = execute_write(query, params, self.db_path)

        return ProductContext(
            product_id=product_id,
            name=create.name,
            product_type=create.product_type,
            category=create.category,
            target_customers=create.target_customers,
            primary_use_case=create.primary_use_case,
            key_features=create.key_features or [],
            description=create.description,
            vibe_key=create.vibe_key,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            vibe=vibe,
        )

    def get_product(self, product_id: int) -> Optional[ProductContext]:
        """
        Get a product context by ID.

        Args:
            product_id: Product ID

        Returns:
            ProductContext with loaded vibe, or None if not found
        """
        query = "SELECT * FROM products WHERE product_id = ?"
        row = execute_query(query, (product_id,), self.db_path, fetch="one")

        if not row:
            return None

        return self._row_to_context(row)

    def get_product_by_name(self, name: str) -> Optional[ProductContext]:
        """
        Get a product context by name.

        Args:
            name: Product name

        Returns:
            ProductContext with loaded vibe, or None if not found
        """
        query = "SELECT * FROM products WHERE name = ?"
        row = execute_query(query, (name,), self.db_path, fetch="one")

        if not row:
            return None

        return self._row_to_context(row)

    def list_products(self) -> List[ProductContext]:
        """
        List all product contexts.

        Returns:
            List of ProductContext objects with loaded vibes
        """
        query = "SELECT * FROM products ORDER BY created_at DESC"
        rows = execute_query(query, (), self.db_path, fetch="all")

        return [self._row_to_context(row) for row in rows]

    def update_product(self, product_id: int, update: ProductContextUpdate) -> Optional[ProductContext]:
        """
        Update a product context.

        Args:
            product_id: Product ID to update
            update: Update data

        Returns:
            Updated ProductContext, or None if not found
        """
        # Check if product exists
        existing = self.get_product(product_id)
        if not existing:
            return None

        # Build update query dynamically
        fields = []
        params = []

        if update.name is not None:
            fields.append("name = ?")
            params.append(update.name)
        if update.product_type is not None:
            fields.append("product_type = ?")
            params.append(update.product_type)
        if update.category is not None:
            fields.append("category = ?")
            params.append(update.category)
        if update.target_customers is not None:
            fields.append("target_customers = ?")
            params.append(update.target_customers)
        if update.primary_use_case is not None:
            fields.append("primary_use_case = ?")
            params.append(update.primary_use_case)
        if update.key_features is not None:
            fields.append("key_features = ?")
            params.append(json.dumps(update.key_features))
        if update.description is not None:
            fields.append("description = ?")
            params.append(update.description)
        if update.vibe_key is not None:
            # Validate new vibe_key
            load_vibe_config(update.vibe_key)
            fields.append("vibe_key = ?")
            params.append(update.vibe_key)

        if not fields:
            return existing  # No changes

        params.append(product_id)
        query = f"UPDATE products SET {', '.join(fields)} WHERE product_id = ?"

        execute_write(query, tuple(params), self.db_path)

        return self.get_product(product_id)

    def delete_product(self, product_id: int) -> bool:
        """
        Delete a product context (cascades to related data).

        Args:
            product_id: Product ID to delete

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM products WHERE product_id = ?"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (product_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_active_product(self, product_id: int) -> Optional[ProductContext]:
        """
        Set a product as the active context for the current session.

        Args:
            product_id: Product ID to activate

        Returns:
            Activated ProductContext, or None if not found
        """
        product = self.get_product(product_id)
        if not product:
            return None

        # Deactivate all products first, then activate the selected one
        with get_connection(self.db_path) as conn:
            conn.execute("UPDATE products SET is_active = 0 WHERE is_active = 1")
            conn.execute("UPDATE products SET is_active = 1 WHERE product_id = ?", (product_id,))
            conn.commit()

        # Set the global active vibe for the session
        if product.vibe:
            set_active_vibe(product.vibe)

        # Return updated product with is_active = True
        return self.get_product(product_id)

    def get_active_product(self) -> Optional[ProductContext]:
        """
        Get the currently active product context using explicit is_active flag.

        Returns:
            Active ProductContext, or None if no active product
        """
        query = "SELECT * FROM products WHERE is_active = 1 LIMIT 1"
        row = execute_query(query, (), self.db_path, fetch="one")

        if not row:
            return None

        return self._row_to_context(row)

    def _row_to_context(self, row: dict) -> ProductContext:
        """Convert database row to ProductContext with loaded vibe."""
        key_features = json.loads(row["key_features"]) if row["key_features"] else []

        vibe = load_vibe_config(row["vibe_key"])

        return ProductContext(
            product_id=row["product_id"],
            name=row["name"],
            product_type=row["product_type"],
            category=row["category"],
            target_customers=row["target_customers"],
            primary_use_case=row["primary_use_case"],
            key_features=key_features,
            description=row["description"],
            vibe_key=row["vibe_key"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
            vibe=vibe,
        )


# Global repository instance
_repository: Optional[ProductContextRepository] = None


def get_repository(db_path: Optional[Path] = None) -> ProductContextRepository:
    """Get or create the global product context repository."""
    global _repository
    if _repository is None:
        _repository = ProductContextRepository(db_path)
    return _repository