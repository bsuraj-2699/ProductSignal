"""
Tests for the Phase 3.1 classification schema extension and migration.

Covers:
  A. Fresh empty database initialization
  B. Migration of a pre-Phase-3 database with duplicate classifications
  C. Idempotency of repeated initialization
  D. Partial migration (some columns exist, index missing)
  E. One-active-classification-per-feedback uniqueness
  F. classification_attempts table constraints

All tests use isolated temporary databases. The real data/productsignal.db is
never touched.
"""

import sqlite3
from pathlib import Path

import pytest

from productsignal.db.connection import (
    check_database_health,
    get_connection,
    initialize_database,
)

NEW_CLASSIFICATION_COLUMNS = {
    "evidence_quotes": "TEXT",
    "classification_reasoning": "TEXT",
    "mentioned_feature": "TEXT",
    "is_actionable": "BOOLEAN",
    "classification_status": "TEXT",
    "model_name": "TEXT",
    "prompt_version": "TEXT",
    "error_note": "TEXT",
}

EXPECTED_ATTEMPT_COLUMNS = {
    "attempt_id", "feedback_id", "product_id", "model_name", "prompt_version",
    "attempt_number", "error_type", "error_detail", "raw_response", "attempted_at",
}

# Exact pre-Phase-3 DDL (captured from a database created with the Phase 2
# schema). products and feedback are unchanged by Phase 3.1; classifications
# lacks every new column and the partial unique index.
PRE_PHASE3_SCHEMA = """
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (product_type IN ('service_based', 'consumer_facing')),
    category TEXT NOT NULL,
    target_customers TEXT,
    primary_use_case TEXT,
    key_features TEXT,
    description TEXT,
    vibe_key TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    external_id TEXT,
    content_hash TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMP,
    customer_segment TEXT,
    product_area TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    original_category TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);
CREATE TABLE classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    primary_category TEXT NOT NULL,
    secondary_category TEXT,
    inferred_product_area TEXT,
    sentiment TEXT CHECK (sentiment IN ('positive', 'negative', 'neutral', 'mixed')),
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    customer_intent TEXT,
    summary TEXT,
    confidence REAL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    needs_review BOOLEAN DEFAULT FALSE,
    model_version TEXT,
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);
"""


def _get_column_map(db_path: Path, table: str) -> dict:
    with get_connection(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"]: row for row in rows}


def _get_index_names(db_path: Path, table: str) -> set:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
            (table,),
        ).fetchall()
        return {row["name"] for row in rows}


def _get_all_classifications(db_path: Path) -> list:
    """Snapshot of classification rows that works both before and after migration
    (does not reference classification_status)."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT classification_id, feedback_id FROM classifications ORDER BY classification_id"
        ).fetchall()


def _get_classification_statuses(db_path: Path) -> dict:
    """Map of classification_id -> classification_status. Post-migration only."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT classification_id, classification_status FROM classifications ORDER BY classification_id"
        ).fetchall()
        return {row["classification_id"]: row["classification_status"] for row in rows}


def _create_pre_phase3_db(db_path: Path) -> tuple:
    """Create a database using the pre-Phase-3 schema and seed it with data.

    Returns (product_id, {feedback_id: n_classifications}).
    Feedback 1 gets 3 classification rows, feedback 2 gets 1, feedback 3 none.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(PRE_PHASE3_SCHEMA)
    conn.commit()

    cursor = conn.execute(
        "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
        ("Legacy Product", "service_based", "saas", "saas"),
    )
    product_id = cursor.lastrowid
    feedback_ids = []
    for i in range(3):
        cursor = conn.execute(
            "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
            (product_id, f"hash-{i}", f"Legacy feedback text {i}"),
        )
        feedback_ids.append(cursor.lastrowid)

    # feedback 1: three historical classification rows (simulating a system that
    # stored every classification without a uniqueness rule)
    legacy_values = [
        (feedback_ids[0], product_id, "performance_speed", 0.8),
        (feedback_ids[0], product_id, "workflow_efficiency", 0.7),
        (feedback_ids[0], product_id, "feature_request", 0.9),
        (feedback_ids[1], product_id, "pricing_value", 0.6),
    ]
    for fb_id, prod_id, category, conf in legacy_values:
        conn.execute(
            """INSERT INTO classifications
               (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence)
               VALUES (?, ?, ?, 'negative', 'medium', 'legacy summary', ?)""",
            (fb_id, prod_id, category, conf),
        )
    conn.commit()
    conn.close()
    return product_id, {feedback_ids[0]: 3, feedback_ids[1]: 1, feedback_ids[2]: 0}


@pytest.fixture
def pre_phase3_db(tmp_path):
    """A database created with the pre-Phase-3 schema, seeded with legacy data."""
    db_path = tmp_path / "legacy.db"
    _create_pre_phase3_db(db_path)
    return db_path


class TestScenarioAFreshDatabase:
    """Scenario A: fresh empty database initialization."""

    def test_all_new_columns_exist(self, clean_db):
        cols = _get_column_map(clean_db, "classifications")
        for name, expected_type in NEW_CLASSIFICATION_COLUMNS.items():
            assert name in cols, f"missing column {name}"
            assert cols[name]["type"].upper() == expected_type, f"wrong type for {name}"

    def test_classification_status_notnull_with_default(self, clean_db):
        col = _get_column_map(clean_db, "classifications")["classification_status"]
        assert col["notnull"] == 1
        assert col["dflt_value"] == "'active'"

    def test_classification_attempts_table_exists(self, clean_db):
        cols = set(_get_column_map(clean_db, "classification_attempts").keys())
        assert cols == EXPECTED_ATTEMPT_COLUMNS

    def test_partial_unique_index_exists(self, clean_db):
        assert "uq_classifications_active" in _get_index_names(clean_db, "classifications")

    def test_classification_status_check_enforced(self, clean_db):
        """Fresh installs carry the CHECK constraint allowing only active/superseded."""
        with get_connection(clean_db) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("P", "service_based", "saas", "saas"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "h1", "text"),
            ).lastrowid
            conn.execute(
                "INSERT INTO classifications (feedback_id, product_id, primary_category, classification_status) "
                "VALUES (?, ?, ?, 'superseded')",
                (feedback_id, product_id, "feature_request"),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classifications (feedback_id, product_id, primary_category, classification_status) "
                    "VALUES (?, ?, ?, 'bogus_status')",
                    (feedback_id, product_id, "feature_request"),
                )

    def test_health_reports_all_tables(self, clean_db):
        health = check_database_health(clean_db)
        assert health["status"] == "healthy"
        assert health["table_count"] == 11
        assert "classification_attempts" in health["tables"]

    def test_existing_tables_and_foreign_keys_intact(self, clean_db):
        with get_connection(clean_db) as conn:
            # foreign keys still enforced
            fk = conn.execute("PRAGMA foreign_keys").fetchone()
            assert fk[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classification_attempts "
                    "(feedback_id, product_id, attempt_number, error_type) VALUES (9999, 9999, 1, 'timeout')"
                )
                conn.commit()


class TestScenarioBMigrationFromPrePhase3:
    """Scenario B: existing pre-Phase-3 database with duplicate classifications."""

    def test_migration_adds_columns_and_resolves_duplicates(self, pre_phase3_db):
        db_path = pre_phase3_db

        before = _get_all_classifications(db_path)
        assert len(before) == 4  # 3 for feedback 1, 1 for feedback 2

        initialize_database(db_path)

        # New columns were added
        cols = _get_column_map(db_path, "classifications")
        for name in NEW_CLASSIFICATION_COLUMNS:
            assert name in cols

        # Newest classification per feedback is active, older ones superseded
        rows = _get_all_classifications(db_path)
        assert len(rows) == 4  # nothing deleted
        statuses = _get_classification_statuses(db_path)
        by_feedback = {}
        for row in rows:
            by_feedback.setdefault(row["feedback_id"], []).append(row["classification_id"])

        fb1_ids = [ids for ids in by_feedback.values() if len(ids) == 3][0]
        newest_id = max(fb1_ids)
        assert statuses[newest_id] == "active"
        assert all(statuses[cid] == "superseded" for cid in fb1_ids if cid != newest_id)

        fb2_id = [ids for ids in by_feedback.values() if len(ids) == 1][0][0]
        assert statuses[fb2_id] == "active"

        # The partial unique index now exists
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")

        # classification_attempts table created for the migrated DB too
        assert set(_get_column_map(db_path, "classification_attempts").keys()) == EXPECTED_ATTEMPT_COLUMNS

    def test_migration_preserves_legacy_field_values(self, pre_phase3_db):
        db_path = pre_phase3_db
        with get_connection(db_path) as conn:
            legacy = conn.execute(
                "SELECT classification_id, primary_category, confidence "
                "FROM classifications ORDER BY classification_id"
            ).fetchall()
        snapshot = [(r["classification_id"], r["primary_category"], r["confidence"]) for r in legacy]

        initialize_database(db_path)

        with get_connection(db_path) as conn:
            after = conn.execute(
                "SELECT classification_id, primary_category, confidence "
                "FROM classifications ORDER BY classification_id"
            ).fetchall()
        assert [(r["classification_id"], r["primary_category"], r["confidence"]) for r in after] == snapshot

    def test_migration_failure_rolls_back_migration_transaction(self, pre_phase3_db):
        """On migration failure, the migration's explicit transaction rolls back
        completely — but schema objects created earlier by the schema.sql
        executescript (e.g. classification_attempts) persist. These two scopes
        are distinct and are asserted separately."""
        db_path = pre_phase3_db

        # Pre-migration state: old schema, no new columns, no attempts table
        with get_connection(db_path) as conn:
            cols_before = {r["name"] for r in conn.execute("PRAGMA table_info(classifications)").fetchall()}
            tables_before = {
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
        assert "classification_status" not in cols_before
        assert "classification_attempts" not in tables_before
        rows_before = _get_all_classifications(db_path)

        # Poison the migration: any UPDATE on classifications raises ABORT, so
        # the dedup step fails after the column additions have already run
        # inside the migration transaction.
        with get_connection(db_path) as conn:
            conn.execute(
                "CREATE TRIGGER fail_migration BEFORE UPDATE ON classifications "
                "BEGIN SELECT RAISE(ABORT, 'migration blocked by trigger'); END"
            )
            conn.commit()

        with pytest.raises(RuntimeError, match="Classification schema migration failed and was rolled back"):
            initialize_database(db_path)

        with get_connection(db_path) as conn:
            cols_after = {r["name"] for r in conn.execute("PRAGMA table_info(classifications)").fetchall()}
            tables_after = {
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            indexes_after = {
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='classifications'"
                ).fetchall()
            }

        # executescript() scope: the attempts table (and other schema objects)
        # persisted even though the migration failed
        assert "classification_attempts" in tables_after

        # migration-transaction scope: rolled back completely
        assert "classification_status" not in cols_after  # ALTERs undone
        assert "uq_classifications_active" not in indexes_after  # index never created
        assert _get_all_classifications(db_path) == rows_before  # no data changes

    def test_migration_failure_at_index_creation_rolls_back_dedup(self, pre_phase3_db):
        """Failure during index creation (after the dedup UPDATE committed to the
        transaction) must also roll back the dedup UPDATE itself."""
        db_path = pre_phase3_db

        # Give the DB classification_status directly so statuses are observable,
        # and block index creation with a table whose name collides with it.
        with get_connection(db_path) as conn:
            conn.execute(
                "ALTER TABLE classifications ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'active'"
            )
            conn.execute("CREATE TABLE uq_classifications_active (x)")  # name collision
            conn.commit()

        with get_connection(db_path) as conn:
            rows_before = conn.execute(
                "SELECT classification_id, feedback_id, classification_status FROM classifications "
                "ORDER BY classification_id"
            ).fetchall()
        assert all(r["classification_status"] == "active" for r in rows_before)

        with pytest.raises(RuntimeError, match="Classification schema migration failed and was rolled back"):
            initialize_database(db_path)

        with get_connection(db_path) as conn:
            rows_after = conn.execute(
                "SELECT classification_id, feedback_id, classification_status FROM classifications "
                "ORDER BY classification_id"
            ).fetchall()
            indexes_after = {
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='classifications'"
                ).fetchall()
            }

        # Dedup UPDATE rolled back: every row is active again (nothing demoted)
        assert [(r["classification_id"], r["feedback_id"], r["classification_status"]) for r in rows_after] == \
               [(r["classification_id"], r["feedback_id"], r["classification_status"]) for r in rows_before]
        assert "uq_classifications_active" not in indexes_after
        # The colliding table still exists (created by the test setup, outside
        # the migration transaction)
        with get_connection(db_path) as conn:
            tables_after = {
                r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        assert "uq_classifications_active" in tables_after


class TestMigrationDeduplication:
    """Regression tests for the deduplication rule: only duplicate ACTIVE rows
    are resolved; rows already marked superseded are never reactivated.

    Uses databases where classification_status exists before migration, so the
    pre-migration statuses are explicit and observable.
    """

    def _make_status_db(self, tmp_path, statuses):
        """Create a pre-Phase-3 DB with classification_status manually added and
        explicit per-row statuses ({classification_id: status})."""
        db_path = tmp_path / "dedup.db"
        _create_pre_phase3_db(db_path)
        with get_connection(db_path) as conn:
            conn.execute(
                "ALTER TABLE classifications ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'active'"
            )
            for cid, status in statuses.items():
                conn.execute(
                    "UPDATE classifications SET classification_status = ? WHERE classification_id = ?",
                    (status, cid),
                )
            conn.commit()
        return db_path

    def test_multiple_active_rows_newest_active_survives(self, tmp_path):
        # Rows 1-3 belong to feedback 1; row 4 belongs to feedback 2
        db_path = self._make_status_db(tmp_path, {1: "active", 2: "active", 3: "active", 4: "active"})

        initialize_database(db_path)

        statuses = _get_classification_statuses(db_path)
        assert statuses == {1: "superseded", 2: "superseded", 3: "active", 4: "active"}
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")

    def test_existing_superseded_history_remains_superseded(self, tmp_path):
        # Row 4 (feedback 2's only row) is superseded and must NOT be reactivated
        db_path = self._make_status_db(tmp_path, {1: "superseded", 2: "superseded", 3: "active", 4: "superseded"})

        initialize_database(db_path)

        statuses = _get_classification_statuses(db_path)
        assert statuses == {1: "superseded", 2: "superseded", 3: "active", 4: "superseded"}
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")

    def test_one_active_with_superseded_history_unchanged(self, tmp_path):
        db_path = self._make_status_db(tmp_path, {1: "superseded", 2: "superseded", 3: "active", 4: "active"})

        initialize_database(db_path)

        statuses = _get_classification_statuses(db_path)
        assert statuses == {1: "superseded", 2: "superseded", 3: "active", 4: "active"}
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")

    def test_no_active_row_remains_no_active_row(self, tmp_path):
        db_path = self._make_status_db(
            tmp_path, {1: "superseded", 2: "superseded", 3: "superseded", 4: "superseded"}
        )

        initialize_database(db_path)

        statuses = _get_classification_statuses(db_path)
        assert statuses == {1: "superseded", 2: "superseded", 3: "superseded", 4: "superseded"}
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")

    def test_all_rows_preserved_after_dedup(self, tmp_path):
        """No classification record is ever deleted by the dedup pass."""
        db_path = self._make_status_db(tmp_path, {1: "active", 2: "active", 3: "active", 4: "active"})

        rows_before = _get_all_classifications(db_path)
        initialize_database(db_path)
        rows_after = _get_all_classifications(db_path)

        assert [(r["classification_id"], r["feedback_id"]) for r in rows_after] == \
               [(r["classification_id"], r["feedback_id"]) for r in rows_before]
        assert len(rows_after) == 4


class TestScenarioCIdempotency:
    """Scenario C: repeated initialization is safe and changes nothing."""

    def test_repeated_initialization_no_duplicates(self, pre_phase3_db):
        db_path = pre_phase3_db
        initialize_database(db_path)

        after_first = _get_all_classifications(db_path)
        cols_first = _get_column_map(db_path, "classifications")

        for _ in range(2):
            initialize_database(db_path)

        cols_third = _get_column_map(db_path, "classifications")
        assert set(cols_third) == set(cols_first)  # no duplicate columns possible, same set
        assert _get_all_classifications(db_path) == after_first  # data unchanged

        with get_connection(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'classification_attempts'"
            ).fetchall()
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'uq_classifications_active'"
            ).fetchall()
        assert len(tables) == 1
        assert len(indexes) == 1
        assert check_database_health(db_path)["status"] == "healthy"

    def test_fresh_db_reinitialization_changes_nothing(self, clean_db):
        with get_connection(clean_db) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("P", "service_based", "saas", "saas"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "h1", "text"),
            ).lastrowid
            conn.execute(
                """INSERT INTO classifications
                   (feedback_id, product_id, primary_category, model_name, classification_status)
                   VALUES (?, ?, ?, 'qwen2.5:7b', 'active')""",
                (feedback_id, product_id, "feature_request"),
            )
            conn.commit()

        snapshot = _get_all_classifications(clean_db)
        initialize_database(clean_db)
        initialize_database(clean_db)
        assert _get_all_classifications(clean_db) == snapshot
        assert _get_column_map(clean_db, "classifications")["classification_status"]["dflt_value"] == "'active'"


class TestScenarioDPartialMigration:
    """Scenario D: some new columns exist but the index does not."""

    def test_some_columns_present_others_added(self, pre_phase3_db):
        db_path = pre_phase3_db

        # Manually add two of the eight columns (simulating an interrupted migration)
        with get_connection(db_path) as conn:
            conn.execute("ALTER TABLE classifications ADD COLUMN model_name TEXT")
            conn.execute("ALTER TABLE classifications ADD COLUMN prompt_version TEXT")
            # Tag one row so we can verify existing column data survives migration
            conn.execute(
                "UPDATE classifications SET model_name = 'legacy-model' WHERE classification_id = 1"
            )
            conn.commit()

        initialize_database(db_path)

        cols = _get_column_map(db_path, "classifications")
        for name in NEW_CLASSIFICATION_COLUMNS:
            assert name in cols, f"missing column {name}"

        # Pre-existing column data preserved
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT model_name FROM classifications WHERE classification_id = 1"
            ).fetchone()
        assert row["model_name"] == "legacy-model"

        # Dedup + index completed
        rows = _get_all_classifications(db_path)
        assert len(rows) == 4
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")
        statuses = list(_get_classification_statuses(db_path).values())
        assert statuses.count("active") == 2  # one per feedback that has rows
        assert statuses.count("superseded") == 2

    def test_status_column_present_without_index_deduplicates(self, pre_phase3_db):
        """If classification_status exists but the index is missing for any reason,
        duplicate active rows are resolved before the index is created."""
        db_path = pre_phase3_db

        # Add classification_status manually: all rows default to 'active'
        with get_connection(db_path) as conn:
            conn.execute(
                "ALTER TABLE classifications ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'active'"
            )
            conn.commit()

        with get_connection(db_path) as conn:
            before = conn.execute(
                "SELECT classification_status, COUNT(*) AS n FROM classifications GROUP BY classification_status"
            ).fetchall()
        assert {r["classification_status"]: r["n"] for r in before} == {"active": 4}

        initialize_database(db_path)

        rows = _get_all_classifications(db_path)
        assert "uq_classifications_active" in _get_index_names(db_path, "classifications")
        statuses = _get_classification_statuses(db_path)
        by_feedback = {}
        for row in rows:
            by_feedback.setdefault(row["feedback_id"], []).append(statuses[row["classification_id"]])
        for fb_id, fb_statuses in by_feedback.items():
            assert fb_statuses.count("active") == 1, f"feedback {fb_id} has multiple active rows"

    def test_status_column_without_index_already_deduped_stays_stable(self, pre_phase3_db):
        """A database already consistent (one active + superseded history) but with
        a missing index must not have its history flipped by the dedup pass."""
        db_path = pre_phase3_db
        with get_connection(db_path) as conn:
            conn.execute(
                "ALTER TABLE classifications ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'active'"
            )
            conn.execute("UPDATE classifications SET classification_status = 'superseded' WHERE classification_id IN (1, 2)")
            conn.commit()

        initialize_database(db_path)

        statuses = _get_classification_statuses(db_path)
        # Newest per feedback stays/becomes active, older ones remain superseded
        assert statuses[3] == "active"
        assert statuses[4] == "active"
        assert statuses[1] == "superseded"
        assert statuses[2] == "superseded"


class TestScenarioEActiveUniqueness:
    """Scenario E: at most one active classification per feedback."""

    def _seed(self, db_path):
        with get_connection(db_path) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("P", "service_based", "saas", "saas"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "h1", "text"),
            ).lastrowid
            conn.commit()
        return product_id, feedback_id

    def _insert_classification(self, db_path, product_id, feedback_id, status="active", category="feature_request"):
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO classifications
                   (feedback_id, product_id, primary_category, sentiment, severity, summary, confidence, classification_status)
                   VALUES (?, ?, ?, 'negative', 'low', 's', 0.9, ?)""",
                (feedback_id, product_id, category, status),
            )
            conn.commit()
            return cursor.lastrowid

    def test_second_active_insert_rejected(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        self._insert_classification(clean_db, product_id, feedback_id, status="active")
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            self._insert_classification(clean_db, product_id, feedback_id, status="active")
        # SQLite reports partial unique index violations as a UNIQUE constraint
        # failure on the indexed column; it does not include the index name.
        assert "UNIQUE constraint failed: classifications.feedback_id" in str(exc_info.value)

    def test_superseded_and_new_active_coexist(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        first_id = self._insert_classification(clean_db, product_id, feedback_id, status="active")

        with get_connection(clean_db) as conn:
            conn.execute(
                "UPDATE classifications SET classification_status = 'superseded' WHERE classification_id = ?",
                (first_id,),
            )
            conn.commit()

        second_id = self._insert_classification(clean_db, product_id, feedback_id, status="active")

        statuses = _get_classification_statuses(clean_db)
        assert len(statuses) == 2
        assert statuses[first_id] == "superseded"
        assert statuses[second_id] == "active"

    def test_multiple_feedbacks_can_each_have_active(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        with get_connection(clean_db) as conn:
            feedback_id2 = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "h2", "text 2"),
            ).lastrowid
            conn.commit()

        self._insert_classification(clean_db, product_id, feedback_id, status="active")
        self._insert_classification(clean_db, product_id, feedback_id2, status="active")

        statuses = _get_classification_statuses(clean_db)
        assert len(statuses) == 2
        assert all(status == "active" for status in statuses.values())


class TestScenarioFClassificationAttempts:
    """Scenario F: classification_attempts constraints."""

    def _seed(self, db_path):
        with get_connection(db_path) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("P", "service_based", "saas", "saas"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "h1", "text"),
            ).lastrowid
            conn.commit()
        return product_id, feedback_id

    def _insert_attempt(self, db_path, feedback_id, product_id, attempt_number=1,
                        error_type="invalid_json", raw_response=None, error_detail=None):
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO classification_attempts
                   (feedback_id, product_id, model_name, prompt_version, attempt_number,
                    error_type, error_detail, raw_response)
                   VALUES (?, ?, 'qwen2.5:7b', 'cls-v1', ?, ?, ?, ?)""",
                (feedback_id, product_id, attempt_number, error_type, error_detail, raw_response),
            )
            conn.commit()
            return cursor.lastrowid

    def test_multiple_attempts_for_same_feedback(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        ids = [
            self._insert_attempt(clean_db, feedback_id, product_id, attempt_number=n, error_type="invalid_json")
            for n in (1, 2, 3)
        ]
        with get_connection(clean_db) as conn:
            rows = conn.execute(
                "SELECT attempt_id, attempt_number FROM classification_attempts WHERE feedback_id = ? "
                "ORDER BY attempt_number",
                (feedback_id,),
            ).fetchall()
        assert [r["attempt_id"] for r in rows] == ids
        assert [r["attempt_number"] for r in rows] == [1, 2, 3]

    def test_foreign_keys_enforced(self, clean_db):
        with get_connection(clean_db) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classification_attempts "
                    "(feedback_id, product_id, attempt_number, error_type) VALUES (9999, 9999, 1, 'timeout')"
                )
                conn.commit()

    def test_invalid_error_type_rejected(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        with get_connection(clean_db) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classification_attempts "
                    "(feedback_id, product_id, attempt_number, error_type) VALUES (?, ?, 1, 'weird_error')",
                    (feedback_id, product_id),
                )
                conn.commit()

    def test_invalid_attempt_number_rejected(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        with get_connection(clean_db) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classification_attempts "
                    "(feedback_id, product_id, attempt_number, error_type) VALUES (?, ?, 0, 'timeout')",
                    (feedback_id, product_id),
                )
                conn.commit()

    def test_raw_response_length_limit(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)

        # Exactly 8000 characters: accepted
        self._insert_attempt(clean_db, feedback_id, product_id, raw_response="x" * 8000)
        # NULL: accepted
        self._insert_attempt(clean_db, feedback_id, product_id, attempt_number=2, raw_response=None)
        # 8001 characters: rejected
        with get_connection(clean_db) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO classification_attempts "
                    "(feedback_id, product_id, attempt_number, error_type, raw_response) "
                    "VALUES (?, ?, 3, 'invalid_json', ?)",
                    (feedback_id, product_id, "x" * 8001),
                )
                conn.commit()

    def test_cascade_delete_from_feedback(self, clean_db):
        product_id, feedback_id = self._seed(clean_db)
        self._insert_attempt(clean_db, feedback_id, product_id)
        with get_connection(clean_db) as conn:
            conn.execute("DELETE FROM feedback WHERE feedback_id = ?", (feedback_id,))
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM classification_attempts WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        assert count["n"] == 0
