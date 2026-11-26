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

from .._paths import get_project_root, get_default_db_path

# Phase 3.1 classification columns. Applied idempotently to databases created
# before this phase; fresh installations get them from schema.sql directly.
# Note: ALTER TABLE cannot add CHECK constraints, so on migrated databases the
# classification_status values are enforced by the repository layer and the
# migration itself; the CHECK exists only on fresh installs.
_CLASSIFICATION_MIGRATION_COLUMNS = [
    ("evidence_quotes", "ALTER TABLE classifications ADD COLUMN evidence_quotes TEXT"),
    ("classification_reasoning", "ALTER TABLE classifications ADD COLUMN classification_reasoning TEXT"),
    ("mentioned_feature", "ALTER TABLE classifications ADD COLUMN mentioned_feature TEXT"),
    ("is_actionable", "ALTER TABLE classifications ADD COLUMN is_actionable BOOLEAN"),
    (
        "classification_status",
        "ALTER TABLE classifications ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'active'",
    ),
    ("model_name", "ALTER TABLE classifications ADD COLUMN model_name TEXT"),
    ("prompt_version", "ALTER TABLE classifications ADD COLUMN prompt_version TEXT"),
    ("error_note", "ALTER TABLE classifications ADD COLUMN error_note TEXT"),
]

_UQ_CLASSIFICATIONS_ACTIVE = "uq_classifications_active"


def get_database_path() -> Path:
    """Get the database path from environment or use default."""
    db_path = os.environ.get("PRODUCTSIGNAL_DB_PATH")
    if db_path:
        return Path(db_path)
    return get_default_db_path()


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
    Initialize the database by executing the schema and applying migrations.

    Fresh installations get the complete schema from schema.sql. Databases
    created before Phase 3.1 are brought up to date idempotently by
    _migrate_classification_schema (CREATE TABLE IF NOT EXISTS cannot add
    columns to existing tables).

    Args:
        db_path: Optional custom database path. Uses default if not provided.

    Raises:
        sqlite3.Error: If database initialization fails.
        RuntimeError: If the classification schema migration fails. The
            migration's explicit transaction is rolled back before the error
            is raised; schema objects created by the schema.sql executescript
            beforehand (e.g. new tables) persist.
    """
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_path}")

    with get_connection(path) as conn:
        schema_sql = schema_path.read_text(encoding="utf-8")
        # executescript() autocommits each statement individually (verified: a
        # mid-script failure leaves earlier statements persisted), so the
        # migration below must not rely on this call for atomicity.
        conn.executescript(schema_sql)
        conn.commit()
        _migrate_classification_schema(conn)


def _migrate_classification_schema(conn: sqlite3.Connection) -> None:
    """
    Bring the classifications schema up to the Phase 3.1 shape, idempotently.

    Ordering matters:
      1. Add missing classification columns first.
      2. Only then create the partial unique index that enforces at most one
         active classification per feedback. If the index is absent for any
         reason, duplicate ACTIVE rows are deduplicated first (the active row
         with the greatest classification_id per feedback stays active, other
         duplicate active rows become superseded; rows already superseded are
         never reactivated and nothing is deleted) so index creation cannot
         fail.

    Scope of atomicity: the steps below run in one explicit transaction and
    roll back completely on failure. Changes made earlier by the schema.sql
    executescript (e.g. newly created tables) are NOT part of this transaction
    and persist regardless.
    """
    try:
        conn.execute("BEGIN IMMEDIATE")

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(classifications)").fetchall()
        }
        if not columns:
            raise sqlite3.OperationalError(
                "classifications table is missing; schema.sql did not apply"
            )

        for column_name, alter_sql in _CLASSIFICATION_MIGRATION_COLUMNS:
            if column_name not in columns:
                conn.execute(alter_sql)

        index_exists = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'index' AND name = ? AND tbl_name = 'classifications'",
            (_UQ_CLASSIFICATIONS_ACTIVE,),
        ).fetchone()

        if not index_exists:
            # Resolve duplicate ACTIVE rows only: among currently-active rows
            # for the same feedback, keep the greatest classification_id active
            # and demote the rest. Rows already marked superseded are never
            # touched, so no historical classification is reactivated, and no
            # row is deleted.
            conn.execute(
                """
                UPDATE classifications
                SET classification_status = 'superseded'
                WHERE classification_status = 'active'
                  AND classification_id NOT IN (
                      SELECT MAX(classification_id) FROM classifications
                      WHERE classification_status = 'active'
                      GROUP BY feedback_id
                  )
                """
            )
            conn.execute(
                f"CREATE UNIQUE INDEX {_UQ_CLASSIFICATIONS_ACTIVE} "
                "ON classifications(feedback_id) WHERE classification_status = 'active'"
            )

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise RuntimeError(
            f"Classification schema migration failed and was rolled back: {exc}"
        ) from exc


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
                "products", "feedback", "classifications", "classification_attempts",
                "clusters", "cluster_feedback", "opportunities", "opportunity_evidence",
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