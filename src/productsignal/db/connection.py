"""
Database connection management for ProductSignal.

Provides safe connection handling, foreign key enforcement,
and database initialization.
"""

import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator


def _get_project_root() -> Path:
    """
    Get the project root directory.

    Uses the location of this module to find the project root,
    independent of the current working directory.
    """
    # This file is at src/productsignal/db/connection.py
    # Project root is 3 levels up
    return Path(__file__).resolve().parent.parent.parent


def _get_default_db_path() -> Path:
    """Get the default database path relative to project root."""
    return _get_project_root() / "data" / "productsignal.db"


def get_database_path() -> Path:
    """Get the database path from environment or use default."""
    db_path = os.environ.get("PRODUCTSIGNAL_DB_PATH")
    if db_path:
        return Path(db_path)
    return _get_default_db_path()


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Get a database connection with proper configuration.

    Args:
        db_path: Optional custom database path. Uses default if not provided.

    Yields:
        Configured sqlite3.Connection with foreign keys enabled and WAL mode.

    Example:
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM products")
            rows = cursor.fetchall()
    """
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    try:
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode = WAL")
        # Return rows as dictionaries
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def initialize_database(db_path: Optional[Path] = None) -> None:
    """
    Initialize the database by executing the schema.

    Args:
        db_path: Optional custom database path. Uses default if not provided.

    Raises:
        sqlite3.Error: If database initialization fails.
    """
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_path}")

    with get_connection(path) as conn:
        schema_sql = schema_path.read_text(encoding="utf-8")
        # Execute multiple statements
        conn.executescript(schema_sql)
        conn.commit()


def check_database_health(db_path: Optional[Path] = None) -> dict:
    """
    Check database health and return status information.

    Args:
        db_path: Optional custom database path.

    Returns:
        Dictionary with health check results.
    """
    path = db_path or get_database_path()

    if not path.exists():
        return {"status": "not_found", "path": str(path)}

    try:
        with get_connection(path) as conn:
            # Check foreign keys are enabled
            fk_result = conn.execute("PRAGMA foreign_keys").fetchone()
            foreign_keys_enabled = fk_result[0] == 1 if fk_result else False

            # Check WAL mode
            wal_result = conn.execute("PRAGMA journal_mode").fetchone()
            wal_mode = wal_result[0].lower() == "wal" if wal_result else False

            # Count tables
            tables_result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tables = [row[0] for row in tables_result]

            # Verify expected tables exist
            expected_tables = {
                "products", "feedback", "classifications", "clusters",
                "cluster_feedback", "opportunities", "opportunity_evidence",
                "briefs", "experiments", "prds"
            }
            missing_tables = expected_tables - set(tables)

            return {
                "status": "healthy" if not missing_tables else "incomplete",
                "path": str(path),
                "foreign_keys_enabled": foreign_keys_enabled,
                "wal_mode": wal_mode,
                "tables": tables,
                "missing_tables": list(missing_tables),
                "table_count": len(tables)
            }
    except sqlite3.Error as e:
        return {"status": "error", "path": str(path), "error": str(e)}


def execute_query(
    query: str,
    params: tuple = (),
    db_path: Optional[Path] = None,
    fetch: str = "all"
) -> list:
    """
    Execute a parameterized query safely.

    Args:
        query: SQL query with placeholders (?)
        params: Query parameters
        db_path: Optional custom database path
        fetch: "all", "one", or "none"

    Returns:
        Query results as list of sqlite3.Row objects
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        if fetch == "all":
            return cursor.fetchall()
        elif fetch == "one":
            return cursor.fetchone()
        return []


def execute_write(
    query: str,
    params: tuple = (),
    db_path: Optional[Path] = None
) -> int:
    """
    Execute a write query (INSERT, UPDATE, DELETE) and return lastrowid.

    Args:
        query: SQL query with placeholders (?)
        params: Query parameters
        db_path: Optional custom database path

    Returns:
        Last inserted row ID
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.lastrowid