"""
Tests for the Phase 3.1 classification repository.

Covers model-level validation through to persistence: active uniqueness,
history, reclassification (incl. transaction rollback), human corrections,
unclassified feedback selection, product queries, and classification attempts.

All tests use isolated temporary databases via the clean_db fixture; the real
data/productsignal.db is never touched.
"""

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from productsignal.db.connection import get_connection
from productsignal.models.classification import (
    ClassificationCreate,
    EvidenceQuote,
    VALID_ATTEMPT_ERROR_TYPES,
)
from productsignal.classification.repository import ClassificationRepository


def _seed_product_feedback(db_path: Path, n_feedback: int = 1) -> tuple:
    """Create a product and n feedback records; returns (product_id, feedback_ids)."""
    with get_connection(db_path) as conn:
        product_id = conn.execute(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Test Product", "service_based", "saas", "saas"),
        ).lastrowid
        feedback_ids = []
        for i in range(n_feedback):
            feedback_ids.append(
                conn.execute(
                    "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                    (product_id, f"hash-{i}", f"Feedback text {i}"),
                ).lastrowid
            )
        conn.commit()
    return product_id, feedback_ids


def _make_create(feedback_id: int, product_id: int, **overrides) -> ClassificationCreate:
    kwargs = {
        "feedback_id": feedback_id,
        "product_id": product_id,
        "primary_category": "reliability_downtime",
        "sentiment": "negative",
        "severity": "high",
        "summary": "Dashboard crashes on load",
        "confidence": 0.9,
        "evidence_quotes": [
            EvidenceQuote(quote="crashes on load", supports="category"),
            EvidenceQuote(quote="crashes", supports="severity"),
        ],
        "classification_reasoning": "Crash wording indicates a reliability issue",
        "mentioned_feature": "dashboard",
        "is_actionable": True,
        "model_name": "qwen2.5:7b",
        "prompt_version": "cls-v1",
    }
    kwargs.update(overrides)
    return ClassificationCreate(**kwargs)


@pytest.fixture
def repo(clean_db):
    return ClassificationRepository(clean_db)


@pytest.fixture
def seeded(clean_db):
    """A clean DB with one product and two feedback records."""
    product_id, feedback_ids = _seed_product_feedback(clean_db, n_feedback=2)
    return clean_db, ClassificationRepository(clean_db), product_id, feedback_ids


class TestInsertAndRetrieve:
    """Insert, retrieval, and round-trip of all fields."""

    def test_insert_and_get_active_roundtrip(self, seeded):
        db_path, repo, product_id, feedback_ids = seeded
        create = _make_create(feedback_ids[0], product_id)

        stored = repo.insert_classification(create)

        assert stored.classification_id > 0
        assert stored.classification_status == "active"
        assert stored.classified_at is not None

        active = repo.get_active_classification(feedback_ids[0])
        assert active is not None
        assert active.classification_id == stored.classification_id
        assert active.primary_category == "reliability_downtime"
        assert active.secondary_category is None
        assert active.sentiment == "negative"
        assert active.severity == "high"
        assert active.confidence == 0.9
        assert active.needs_review is False
        assert active.model_name == "qwen2.5:7b"
        assert active.prompt_version == "cls-v1"
        assert active.classification_reasoning == "Crash wording indicates a reliability issue"
        assert active.mentioned_feature == "dashboard"
        assert active.is_actionable is True
        assert [q.model_dump() for q in active.evidence_quotes] == [
            {"quote": "crashes on load", "supports": "category"},
            {"quote": "crashes", "supports": "severity"},
        ]

    def test_get_active_returns_none_without_classification(self, seeded):
        _, repo, _, feedback_ids = seeded
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_get_classification_by_id(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        stored = repo.insert_classification(_make_create(feedback_ids[0], product_id))
        fetched = repo.get_classification(stored.classification_id)
        assert fetched is not None
        assert fetched.classification_id == stored.classification_id
        assert repo.get_classification(999999) is None

    def test_insert_with_null_confidence(self, seeded):
        """Deterministic fallback row: confidence NULL, needs_review forced True."""
        _, repo, product_id, feedback_ids = seeded
        create = _make_create(
            feedback_ids[0],
            product_id,
            primary_category="other_unclear",
            sentiment="neutral",
            severity="low",
            confidence=None,
            needs_review=True,
            is_actionable=False,
            evidence_quotes=None,
            classification_reasoning="Deterministic fallback: content insufficient",
            model_name="deterministic",
        )
        stored = repo.insert_classification(create)
        assert stored.confidence is None
        assert stored.model_name == "deterministic"

        active = repo.get_active_classification(feedback_ids[0])
        assert active.confidence is None

    def test_insert_missing_feedback_rejected(self, seeded):
        """The consistency pre-check rejects nonexistent feedback with a clear
        ValueError before any INSERT runs (the FK constraint remains a backstop)."""
        _, repo, product_id, _ = seeded
        with pytest.raises(ValueError, match="does not exist"):
            repo.insert_classification(_make_create(999999, product_id))
        assert repo.get_classification_history(999999) == []

    def test_insert_invalid_status_rejected_at_repository_level(self, seeded):
        """The repository must enforce the status vocabulary even when a value
        bypasses Pydantic validation (model_copy does not re-validate)."""
        _, repo, product_id, feedback_ids = seeded
        create = _make_create(feedback_ids[0], product_id).model_copy(
            update={"classification_status": "pending"}
        )
        with pytest.raises(ValueError, match="Invalid classification_status"):
            repo.insert_classification(create)
        assert repo.get_active_classification(feedback_ids[0]) is None


class TestActiveUniquenessAndHistory:
    """One active classification per feedback; full history preserved."""

    def test_second_active_insert_rejected(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.insert_classification(_make_create(feedback_ids[0], product_id))
        with pytest.raises(sqlite3.IntegrityError):
            repo.insert_classification(_make_create(feedback_ids[0], product_id))

    def test_superseded_and_new_active_coexist(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        assert repo.supersede_classification(first.classification_id) is True

        second = repo.insert_classification(
            _make_create(feedback_ids[0], product_id, primary_category="feature_request")
        )

        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == second.classification_id

        history = repo.get_classification_history(feedback_ids[0])
        assert len(history) == 2
        assert [c.classification_id for c in history] == [second.classification_id, first.classification_id]
        assert history[1].classification_status == "superseded"
        assert history[1].primary_category == "reliability_downtime"  # preserved verbatim

    def test_supersede_nonexistent_or_already_superseded_returns_false(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        assert repo.supersede_classification(999999) is False

        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))
        assert repo.supersede_classification(first.classification_id) is True
        # Already superseded: not modified again
        assert repo.supersede_classification(first.classification_id) is False

    def test_history_empty_for_unclassified_feedback(self, seeded):
        _, repo, _, feedback_ids = seeded
        assert repo.get_classification_history(feedback_ids[1]) == []


class TestReclassification:
    """Validate-then-replace semantics with transactional rollback."""

    def test_reclassification_supersedes_and_inserts(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        replacement = repo.reclassify(
            _make_create(feedback_ids[0], product_id, primary_category="performance_speed")
        )

        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == replacement.classification_id
        assert active.primary_category == "performance_speed"

        old = repo.get_classification(first.classification_id)
        assert old.classification_status == "superseded"  # preserved, not deleted

    def test_reclassification_first_insert_without_existing_active(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        result = repo.reclassify(_make_create(feedback_ids[0], product_id))
        assert result.classification_status == "active"
        assert repo.get_active_classification(feedback_ids[0]) is not None

    def test_reclassification_rollback_restores_old_active(self, seeded):
        """If the insert fails, the old active classification is restored and no
        partial state persists."""
        db_path, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        # Poison all future INSERTs on classifications
        with get_connection(db_path) as conn:
            conn.execute(
                "CREATE TRIGGER fail_reclassify BEFORE INSERT ON classifications "
                "BEGIN SELECT RAISE(ABORT, 'reclassification blocked by trigger'); END"
            )
            conn.commit()

        with pytest.raises(RuntimeError, match="rolled back"):
            repo.reclassify(
                _make_create(feedback_ids[0], product_id, primary_category="performance_speed")
            )

        # Old active classification fully restored
        active = repo.get_active_classification(feedback_ids[0])
        assert active is not None
        assert active.classification_id == first.classification_id
        assert active.classification_status == "active"
        assert active.primary_category == "reliability_downtime"

        with get_connection(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM classifications WHERE feedback_id = ?",
                (feedback_ids[0],),
            ).fetchone()
        assert count["n"] == 1  # no orphan superseded row, no inserted row

    def test_reclassify_rejects_non_active_status(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.insert_classification(_make_create(feedback_ids[0], product_id))
        rows_before = repo.get_classification_history(feedback_ids[0])

        bad = _make_create(feedback_ids[0], product_id).model_copy(
            update={"classification_status": "superseded"}
        )
        with pytest.raises(ValueError, match="must insert an 'active'"):
            repo.reclassify(bad)

        # DB unchanged
        assert repo.get_classification_history(feedback_ids[0]) == rows_before
        assert repo.get_active_classification(feedback_ids[0]).classification_status == "active"

    def test_invalid_model_validation_happens_before_any_db_change(self, seeded):
        """An invalid new classification can never reach the database, so the old
        active record cannot be modified by a failed reclassification."""
        _, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        with pytest.raises(ValidationError):
            _make_create(feedback_ids[0], product_id, sentiment="hostile")

        # Nothing changed
        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == first.classification_id
        assert active.classification_status == "active"


class TestHumanCorrections:
    """Human corrections preserve model history and clear needs_review."""

    def test_human_correction_preserves_original(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(
            _make_create(feedback_ids[0], product_id, needs_review=True)
        )

        correction = repo.save_human_correction(
            feedback_ids[0],
            _make_create(
                feedback_ids[0],
                product_id,
                primary_category="workflow_efficiency",
                model_name="qwen2.5:7b",  # ignored — must be forced to 'human'
                needs_review=True,        # ignored — must be cleared
            ),
        )

        # New active row is the human correction
        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == correction.classification_id
        assert active.model_name == "human"
        assert active.classification_status == "active"
        assert active.needs_review is False
        assert active.primary_category == "workflow_efficiency"

        # Original model classification preserved as superseded history
        original_after = repo.get_classification(original.classification_id)
        assert original_after.classification_status == "superseded"
        assert original_after.model_name == "qwen2.5:7b"
        assert original_after.primary_category == "reliability_downtime"
        assert original_after.needs_review is True  # historical flag untouched

        history = repo.get_classification_history(feedback_ids[0])
        assert len(history) == 2

    def test_human_correction_rollback_restores_previous_active(self, seeded):
        db_path, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        with get_connection(db_path) as conn:
            conn.execute(
                "CREATE TRIGGER fail_correction BEFORE INSERT ON classifications "
                "BEGIN SELECT RAISE(ABORT, 'correction blocked by trigger'); END"
            )
            conn.commit()

        with pytest.raises(RuntimeError, match="rolled back"):
            repo.save_human_correction(
                feedback_ids[0],
                _make_create(feedback_ids[0], product_id, primary_category="workflow_efficiency"),
            )

        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == original.classification_id
        assert active.model_name == "qwen2.5:7b"
        assert active.classification_status == "active"


class TestUnclassifiedFeedback:
    """Selection of feedback records without an active classification."""

    def test_lists_only_unclassified(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.insert_classification(_make_create(feedback_ids[0], product_id))

        unclassified = repo.get_unclassified_feedback_ids(product_id)
        assert unclassified == [feedback_ids[1]]

    def test_returns_all_when_none_classified(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        assert repo.get_unclassified_feedback_ids(product_id) == sorted(feedback_ids)

    def test_limit(self, seeded):
        _, repo, product_id, _ = seeded
        assert len(repo.get_unclassified_feedback_ids(product_id, limit=1)) == 1

    def test_superseded_only_feedback_counts_as_unclassified(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))
        repo.supersede_classification(first.classification_id)

        assert feedback_ids[0] in repo.get_unclassified_feedback_ids(product_id)

    def test_reclassified_feedback_stays_classified(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.insert_classification(_make_create(feedback_ids[0], product_id))
        repo.reclassify(_make_create(feedback_ids[0], product_id))

        assert feedback_ids[0] not in repo.get_unclassified_feedback_ids(product_id)


class TestProductQueries:
    """Retrieval of classifications by product."""

    def _second_product(self, db_path):
        with get_connection(db_path) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("Other Product", "consumer_facing", "mobile_app", "saas"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "hash-other", "Other product feedback"),
            ).lastrowid
            conn.commit()
        return product_id, feedback_id

    def test_active_only_by_default(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        first = repo.insert_classification(_make_create(feedback_ids[0], product_id))
        repo.reclassify(_make_create(feedback_ids[0], product_id))
        repo.insert_classification(_make_create(feedback_ids[1], product_id))

        results = repo.get_product_classifications(product_id)
        assert len(results) == 2  # two feedback records, one active each
        assert all(c.classification_status == "active" for c in results)

    def test_include_history(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.insert_classification(_make_create(feedback_ids[0], product_id))
        repo.reclassify(_make_create(feedback_ids[0], product_id))

        results = repo.get_product_classifications(product_id, active_only=False)
        assert len(results) == 2  # 1 superseded + 1 active

    def test_scoped_to_product(self, seeded):
        db_path, repo, product_id, feedback_ids = seeded
        other_product, other_feedback = self._second_product(db_path)
        repo.insert_classification(_make_create(feedback_ids[0], product_id))
        repo.insert_classification(_make_create(other_feedback, other_product))

        assert len(repo.get_product_classifications(product_id)) == 1
        assert len(repo.get_product_classifications(other_product)) == 1


class TestClassificationAttempts:
    """Failed attempts are stored separately with truncation and validation."""

    def test_record_and_retrieve_multiple_attempts(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        ids = [
            repo.record_attempt(
                feedback_ids[0], product_id, attempt_number=n,
                error_type="invalid_json", error_detail="JSONDecodeError at char 3",
                raw_response="not json {", model_name="qwen2.5:7b", prompt_version="cls-v1",
            )
            for n in (1, 2, 3)
        ]

        attempts = repo.get_attempts_for_feedback(feedback_ids[0])
        assert [a.attempt_id for a in attempts] == ids
        assert [a.attempt_number for a in attempts] == [1, 2, 3]
        assert all(a.error_type == "invalid_json" for a in attempts)
        assert attempts[0].error_detail == "JSONDecodeError at char 3"
        assert attempts[0].model_name == "qwen2.5:7b"

    def test_all_valid_error_types_accepted(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        for n, error_type in enumerate(VALID_ATTEMPT_ERROR_TYPES, start=1):
            attempt_id = repo.record_attempt(
                feedback_ids[0], product_id, attempt_number=n, error_type=error_type
            )
            assert attempt_id > 0

        attempts = repo.get_attempts_for_feedback(feedback_ids[0])
        assert [a.error_type for a in attempts] == list(VALID_ATTEMPT_ERROR_TYPES)

    def test_invalid_error_type_rejected(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        with pytest.raises(ValueError, match="Invalid attempt error_type"):
            repo.record_attempt(
                feedback_ids[0], product_id, attempt_number=1, error_type="weird_error"
            )
        assert repo.get_attempts_for_feedback(feedback_ids[0]) == []

    def test_raw_response_truncated_to_8000(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.record_attempt(
            feedback_ids[0], product_id, attempt_number=1,
            error_type="provider_error", raw_response="x" * 9000,
        )

        attempts = repo.get_attempts_for_feedback(feedback_ids[0])
        assert len(attempts[0].raw_response) == 8000
        assert set(attempts[0].raw_response) == {"x"}

    def test_raw_response_at_limit_not_truncated(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.record_attempt(
            feedback_ids[0], product_id, attempt_number=1,
            error_type="provider_error", raw_response="y" * 8000,
        )
        assert len(repo.get_attempts_for_feedback(feedback_ids[0])[0].raw_response) == 8000

    def test_raw_response_none_allowed(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        repo.record_attempt(
            feedback_ids[0], product_id, attempt_number=1,
            error_type="timeout", raw_response=None,
        )
        assert repo.get_attempts_for_feedback(feedback_ids[0])[0].raw_response is None

    def test_attempt_missing_feedback_rejected(self, seeded):
        """Nonexistent feedback is caught by the consistency pre-check (ValueError)
        before the FK constraint would raise IntegrityError."""
        _, repo, _, _ = seeded
        with pytest.raises(ValueError, match="does not exist"):
            repo.record_attempt(999999, 999999, attempt_number=1, error_type="timeout")
        assert repo.get_attempts_for_feedback(999999) == []

    def test_attempt_wrong_product_rejected(self, seeded):
        """A real feedback with a product it doesn't belong to is caught by the
        consistency pre-check (ValueError) before the FK would ever raise."""
        _, repo, product_id, feedback_ids = seeded
        with pytest.raises(ValueError, match="belongs to product"):
            repo.record_attempt(feedback_ids[0], 999999, attempt_number=1, error_type="timeout")
        assert repo.get_attempts_for_feedback(feedback_ids[0]) == []

    def test_attempts_do_not_affect_classification_lifecycle(self, seeded):
        """Recording attempts never creates or modifies classification rows."""
        _, repo, product_id, feedback_ids = seeded
        repo.record_attempt(feedback_ids[0], product_id, attempt_number=1, error_type="timeout")

        assert repo.get_active_classification(feedback_ids[0]) is None
        assert repo.get_classification_history(feedback_ids[0]) == []
        assert feedback_ids[0] in repo.get_unclassified_feedback_ids(product_id)


class TestRepositoryValidationWithoutSchemaChecks:
    """Status vocabulary enforcement independent of database CHECK constraints."""

    def test_status_validation_on_migrated_db(self, tmp_path):
        """A database whose classifications table lacks the CHECK constraint
        (simulating a migrated pre-Phase-3 DB) still rejects invalid statuses."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_classification_schema_migration import _create_pre_phase3_db

        db_path = tmp_path / "migrated.db"
        _create_pre_phase3_db(db_path)

        from productsignal.db.connection import initialize_database
        initialize_database(db_path)  # adds columns via migration (no CHECK)

        repo = ClassificationRepository(db_path)
        product_id, feedback_ids = _seed_product_feedback(db_path, n_feedback=1)

        create = _make_create(feedback_ids[0], product_id).model_copy(
            update={"classification_status": "archived"}
        )
        with pytest.raises(ValueError, match="Invalid classification_status"):
            repo.insert_classification(create)

        # Valid statuses still work on the migrated DB
        stored = repo.insert_classification(_make_create(feedback_ids[0], product_id))
        assert stored.classification_status == "active"


@pytest.fixture
def two_products(clean_db):
    """Two valid products, each with their own feedback records."""
    with get_connection(clean_db) as conn:
        product_a = conn.execute(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Product A", "service_based", "saas", "saas"),
        ).lastrowid
        feedback_a = conn.execute(
            "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
            (product_a, "hash-a", "Feedback for product A"),
        ).lastrowid
        product_b = conn.execute(
            "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
            ("Product B", "consumer_facing", "mobile_app", "saas"),
        ).lastrowid
        feedback_b = conn.execute(
            "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
            (product_b, "hash-b", "Feedback for product B"),
        ).lastrowid
        conn.commit()
    return clean_db, ClassificationRepository(clean_db), product_a, feedback_a, product_b, feedback_b


class TestFeedbackProductConsistency:
    """Feedback/product association is verified before any write (Issue 1)."""

    def test_insert_mismatched_product_rejected(self, two_products):
        db_path, repo, product_a, feedback_a, product_b, _ = two_products
        with pytest.raises(ValueError, match="belongs to product"):
            repo.insert_classification(_make_create(feedback_a, product_b))

        assert repo.get_active_classification(feedback_a) is None
        assert repo.get_classification_history(feedback_a) == []
        assert repo.get_product_classifications(product_b) == []

    def test_insert_matched_product_succeeds_for_both_products(self, two_products):
        _, repo, product_a, feedback_a, product_b, feedback_b = two_products
        stored_a = repo.insert_classification(_make_create(feedback_a, product_a))
        stored_b = repo.insert_classification(_make_create(feedback_b, product_b))

        assert repo.get_active_classification(feedback_a).classification_id == stored_a.classification_id
        assert repo.get_active_classification(feedback_b).classification_id == stored_b.classification_id
        assert [c.classification_id for c in repo.get_product_classifications(product_a)] == [stored_a.classification_id]
        assert [c.classification_id for c in repo.get_product_classifications(product_b)] == [stored_b.classification_id]

    def test_reclassify_mismatched_product_rejected_and_old_active_preserved(self, two_products):
        _, repo, product_a, feedback_a, product_b, _ = two_products
        original = repo.insert_classification(_make_create(feedback_a, product_a))

        with pytest.raises(ValueError, match="belongs to product"):
            repo.reclassify(
                _make_create(feedback_a, product_b, primary_category="performance_speed")
            )

        active = repo.get_active_classification(feedback_a)
        assert active.classification_id == original.classification_id
        assert active.classification_status == "active"
        assert active.primary_category == "reliability_downtime"
        assert repo.get_classification_history(feedback_a) == [active]  # nothing superseded

    def test_human_correction_mismatched_product_rejected_before_supersede(self, two_products):
        _, repo, product_a, feedback_a, product_b, _ = two_products
        original = repo.insert_classification(_make_create(feedback_a, product_a))

        # Correction carries product B's id but targets product A's feedback
        correction = _make_create(feedback_a, product_b, primary_category="workflow_efficiency")
        with pytest.raises(ValueError, match="belongs to product"):
            repo.save_human_correction(feedback_a, correction)

        # Original classification untouched — not superseded, still active
        active = repo.get_active_classification(feedback_a)
        assert active.classification_id == original.classification_id
        assert active.classification_status == "active"
        assert active.model_name == "qwen2.5:7b"
        assert repo.get_classification_history(feedback_a) == [active]

    def test_human_correction_matched_product_succeeds(self, two_products):
        _, repo, product_a, feedback_a, product_b, feedback_b = two_products
        repo.insert_classification(_make_create(feedback_a, product_a))

        correction = repo.save_human_correction(
            feedback_b,
            _make_create(feedback_b, product_b, primary_category="workflow_efficiency"),
        )
        assert correction.model_name == "human"
        assert repo.get_active_classification(feedback_b).classification_id == correction.classification_id

    def test_record_attempt_mismatched_product_rejected(self, two_products):
        _, repo, product_a, feedback_a, product_b, _ = two_products
        with pytest.raises(ValueError, match="belongs to product"):
            repo.record_attempt(feedback_a, product_b, attempt_number=1, error_type="timeout")

        assert repo.get_attempts_for_feedback(feedback_a) == []

    def test_record_attempt_matched_product_succeeds(self, two_products):
        _, repo, product_a, feedback_a, product_b, feedback_b = two_products
        attempt_a = repo.record_attempt(feedback_a, product_a, attempt_number=1, error_type="timeout")
        attempt_b = repo.record_attempt(feedback_b, product_b, attempt_number=1, error_type="timeout")

        assert attempt_a > 0 and attempt_b > 0
        assert len(repo.get_attempts_for_feedback(feedback_a)) == 1
        assert len(repo.get_attempts_for_feedback(feedback_b)) == 1


class TestRepositoryRejectsInvalidMutatedModels:
    """model_copy(update=...) bypasses Pydantic validation; the repository must
    not persist the resulting invalid fields (Issue 2)."""

    def test_insert_rejects_mutated_sentiment(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(update={"sentiment": "hostile"})
        with pytest.raises(ValueError, match="Invalid sentiment"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_insert_rejects_mutated_severity(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(update={"severity": "apocalyptic"})
        with pytest.raises(ValueError, match="Invalid severity"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_insert_rejects_mutated_confidence(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(update={"confidence": 1.5})
        with pytest.raises(ValueError, match="Confidence must be between"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_insert_rejects_mutated_blank_summary(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(update={"summary": "   "})
        with pytest.raises(ValueError, match="Summary cannot be empty"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_insert_rejects_mutated_evidence_quote_supports(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad_quote = EvidenceQuote(quote="crashes", supports="category").model_copy(
            update={"supports": "fabricated_aspect"}
        )
        bad = _make_create(feedback_ids[0], product_id, evidence_quotes=[bad_quote])
        with pytest.raises(ValueError, match="Invalid evidence quote supports"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_insert_rejects_non_evidence_quote_entries(self, seeded):
        """Raw strings are rejected at construction by Pydantic; the repository
        isinstance check catches the model_copy(update=...) bypass."""
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(
            update={"evidence_quotes": ["crashes on load"]}
        )
        with pytest.raises(ValueError, match="EvidenceQuote instances"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_reclassify_rejects_mutated_fields_and_preserves_old_active(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        bad = _make_create(
            feedback_ids[0], product_id, primary_category="performance_speed"
        ).model_copy(update={"sentiment": "furious"})
        with pytest.raises(ValueError, match="Invalid sentiment"):
            repo.reclassify(bad)

        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == original.classification_id
        assert active.classification_status == "active"
        assert repo.get_classification_history(feedback_ids[0]) == [active]

    def test_human_correction_rejects_mutated_fields(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        bad = _make_create(feedback_ids[0], product_id).model_copy(update={"severity": "cosmic"})
        with pytest.raises(ValueError, match="Invalid severity"):
            repo.save_human_correction(feedback_ids[0], bad)

        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == original.classification_id
        assert active.model_name == "qwen2.5:7b"  # correction never applied

    def test_insert_accepts_valid_secondary_category(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        create = _make_create(feedback_ids[0], product_id, secondary_category="data_accuracy")
        stored = repo.insert_classification(create)
        assert repo.get_active_classification(feedback_ids[0]).secondary_category == "data_accuracy"


CUSTOM_VIBE_YAML = """
product_type: "consumer_facing"
product_category: "legacy_tool"

classification_taxonomy:
  primary_categories:
    - "legacy_export"
    - "custom_category"

scoring_weights:
  frequency: 0.2
  severity: 0.2
  segment_impact: 0.2
  recency: 0.2
  business_relevance: 0.2

provider:
  name: "fake"
  model: "custom-test-model"
"""

EMPTY_TAXONOMY_VIBE_YAML = """
product_type: "consumer_facing"
product_category: "empty_taxonomy"

classification_taxonomy:
  primary_categories: []

scoring_weights:
  frequency: 0.2
  severity: 0.2
  segment_impact: 0.2
  recency: 0.2
  business_relevance: 0.2

provider:
  name: "fake"
  model: "custom-test-model"
"""


class TestProductTaxonomyValidation:
    """Categories are validated against the feedback's product's own vibe
    taxonomy at the repository boundary — including values smuggled in via
    model_copy(update=...) — with no silent fallback to the default taxonomy."""

    @pytest.fixture
    def custom_env(self, tmp_path):
        """A temp DB plus a temp vibe config dir containing a custom taxonomy."""
        from productsignal.config import clear_vibe_cache

        config_dir = tmp_path / "vibes"
        config_dir.mkdir()
        (config_dir / "custom_vibe.yaml").write_text(CUSTOM_VIBE_YAML)
        (config_dir / "empty_taxonomy_vibe.yaml").write_text(EMPTY_TAXONOMY_VIBE_YAML)

        db_path = tmp_path / "taxonomy.db"
        from productsignal.db.connection import initialize_database
        initialize_database(db_path)

        with get_connection(db_path) as conn:
            product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("Custom Product", "consumer_facing", "legacy_tool", "custom_vibe"),
            ).lastrowid
            feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (product_id, "hash-custom", "Custom product feedback"),
            ).lastrowid
            ghost_product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("Ghost Vibe Product", "service_based", "saas", "ghost_vibe"),
            ).lastrowid
            ghost_feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (ghost_product_id, "hash-ghost", "Ghost vibe feedback"),
            ).lastrowid
            empty_product_id = conn.execute(
                "INSERT INTO products (name, product_type, category, vibe_key) VALUES (?, ?, ?, ?)",
                ("Empty Taxonomy Product", "consumer_facing", "legacy_tool", "empty_taxonomy_vibe"),
            ).lastrowid
            empty_feedback_id = conn.execute(
                "INSERT INTO feedback (product_id, content_hash, feedback_text) VALUES (?, ?, ?)",
                (empty_product_id, "hash-empty", "Empty taxonomy feedback"),
            ).lastrowid
            conn.commit()

        clear_vibe_cache()
        repo = ClassificationRepository(db_path, config_dir=config_dir)
        yield db_path, repo, product_id, feedback_id, ghost_feedback_id, empty_feedback_id
        clear_vibe_cache()

    def _custom_create(self, feedback_id, product_id, **overrides):
        """Build a ClassificationCreate valid under the custom taxonomy."""
        from productsignal.models.classification import validate_classification_dict

        data = {
            "feedback_id": feedback_id,
            "product_id": product_id,
            "primary_category": "legacy_export",
            "sentiment": "negative",
            "severity": "high",
            "summary": "Export fails on large files",
            "confidence": 0.8,
        }
        data.update(overrides)
        return validate_classification_dict(
            data, valid_categories=frozenset({"legacy_export", "custom_category"})
        )

    # --- Invalid category via model_copy (default SaaS product) ---

    def test_insert_rejects_mutated_primary_category(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(
            update={"primary_category": "bogus_category"}
        )
        with pytest.raises(ValueError, match="Invalid primary_category.*bogus_category"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None
        assert repo.get_classification_history(feedback_ids[0]) == []

    def test_insert_rejects_mutated_secondary_category(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        bad = _make_create(feedback_ids[0], product_id).model_copy(
            update={"secondary_category": "bogus_category"}
        )
        with pytest.raises(ValueError, match="Invalid secondary_category.*bogus_category"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_ids[0]) is None

    def test_reclassify_rejects_mutated_category_and_preserves_old_active(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        bad = _make_create(
            feedback_ids[0], product_id, primary_category="performance_speed"
        ).model_copy(update={"primary_category": "bogus_category"})
        with pytest.raises(ValueError, match="Invalid primary_category"):
            repo.reclassify(bad)

        # Existing active classification untouched, history unchanged
        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == original.classification_id
        assert active.classification_status == "active"
        assert active.primary_category == "reliability_downtime"
        assert len(repo.get_classification_history(feedback_ids[0])) == 1

    def test_human_correction_rejects_mutated_category_before_supersede(self, seeded):
        _, repo, product_id, feedback_ids = seeded
        original = repo.insert_classification(_make_create(feedback_ids[0], product_id))

        bad = _make_create(feedback_ids[0], product_id).model_copy(
            update={"primary_category": "bogus_category"}
        )
        with pytest.raises(ValueError, match="Invalid primary_category"):
            repo.save_human_correction(feedback_ids[0], bad)

        # Original never superseded
        active = repo.get_active_classification(feedback_ids[0])
        assert active.classification_id == original.classification_id
        assert active.classification_status == "active"
        assert active.model_name == "qwen2.5:7b"
        assert len(repo.get_classification_history(feedback_ids[0])) == 1

    # --- Custom Product Vibe ---

    def test_custom_taxonomy_category_accepted(self, custom_env):
        _, repo, product_id, feedback_id, *_ = custom_env
        create = self._custom_create(feedback_id, product_id)
        stored = repo.insert_classification(create)

        active = repo.get_active_classification(feedback_id)
        assert active.classification_id == stored.classification_id
        assert active.primary_category == "legacy_export"

    def test_default_taxonomy_category_rejected_for_custom_vibe_product(self, custom_env):
        """'reliability_downtime' exists in the default SaaS taxonomy but not in
        this product's custom vibe — it must be rejected, not silently accepted
        via a default-taxonomy fallback."""
        _, repo, product_id, feedback_id, *_ = custom_env
        bad = self._custom_create(feedback_id, product_id).model_copy(
            update={"primary_category": "reliability_downtime"}
        )
        with pytest.raises(ValueError, match="must be one of.*legacy_export"):
            repo.insert_classification(bad)
        assert repo.get_active_classification(feedback_id) is None

    def test_custom_taxonomy_invalid_via_model_copy_rejected(self, custom_env):
        _, repo, product_id, feedback_id, *_ = custom_env
        repo.insert_classification(self._custom_create(feedback_id, product_id))

        bad = self._custom_create(feedback_id, product_id).model_copy(
            update={"primary_category": "totally_made_up"}
        )
        with pytest.raises(ValueError, match="Invalid primary_category"):
            repo.reclassify(bad)

        # Custom-vibe reclassification with a valid custom category still works
        replacement = repo.reclassify(
            self._custom_create(feedback_id, product_id, primary_category="custom_category")
        )
        assert repo.get_active_classification(feedback_id).classification_id == replacement.classification_id

    def test_custom_taxonomy_secondary_category_validated(self, custom_env):
        _, repo, product_id, feedback_id, *_ = custom_env
        good = self._custom_create(feedback_id, product_id, secondary_category="custom_category")
        repo.insert_classification(good)

        bad = self._custom_create(feedback_id, product_id).model_copy(
            update={"secondary_category": "reliability_downtime"}
        )
        with pytest.raises(ValueError, match="Invalid secondary_category"):
            repo.reclassify(bad)

    # --- Failure handling: taxonomy resolution fails safely ---

    def test_missing_vibe_config_fails_safely(self, custom_env):
        """A product whose vibe_key has no configuration file cannot fall back
        to the default taxonomy; persistence must fail with a clear error."""
        _, repo, _, _, ghost_feedback_id, _ = custom_env
        with get_connection(custom_env[0]) as conn:
            ghost_product_id = conn.execute(
                "SELECT product_id FROM feedback WHERE feedback_id = ?", (ghost_feedback_id,)
            ).fetchone()["product_id"]
        create = _make_create(ghost_feedback_id, ghost_product_id)

        with pytest.raises(ValueError, match="Cannot resolve Product Vibe 'ghost_vibe'"):
            repo.insert_classification(create)
        assert repo.get_active_classification(ghost_feedback_id) is None

    def test_empty_taxonomy_fails_safely(self, custom_env):
        _, repo, _, _, _, empty_feedback_id = custom_env
        with get_connection(custom_env[0]) as conn:
            empty_product_id = conn.execute(
                "SELECT product_id FROM feedback WHERE feedback_id = ?", (empty_feedback_id,)
            ).fetchone()["product_id"]

        create = _make_create(empty_feedback_id, empty_product_id)
        with pytest.raises(ValueError, match="defines no.*primary_categories"):
            repo.insert_classification(create)
        assert repo.get_active_classification(empty_feedback_id) is None


