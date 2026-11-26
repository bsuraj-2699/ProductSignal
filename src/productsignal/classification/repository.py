"""
Classification repository for ProductSignal.

Persistence operations for AI-generated feedback classifications and failed
classification attempts. Enforces the one-active-classification-per-feedback
lifecycle on top of the partial unique index, so the invariants hold even on
migrated databases that lack the schema CHECK constraints.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ..db.connection import get_connection
from ..config import load_vibe_config
from ..models.classification import (
    Classification,
    ClassificationAttempt,
    ClassificationCreate,
    EvidenceQuote,
    MAX_RAW_RESPONSE_LENGTH,
    SENTIMENT_VALUES,
    SEVERITY_VALUES,
    VALID_ATTEMPT_ERROR_TYPES,
    VALID_CLASSIFICATION_STATUSES,
)


class ClassificationRepository:
    """Repository for classification records and classification attempts."""

    def __init__(self, db_path: Optional[Path] = None, config_dir: Optional[Path] = None):
        self.db_path = db_path
        # Passed through to load_vibe_config so product-specific taxonomy
        # resolution works with custom configuration directories (mirrors the
        # signature of load_vibe_config itself).
        self.config_dir = config_dir

    # ------------------------------------------------------------------
    # Validation helpers (independent of the database CHECK constraints)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_status(status: str) -> str:
        if status not in VALID_CLASSIFICATION_STATUSES:
            raise ValueError(
                f"Invalid classification_status: {status!r}. "
                f"Must be one of: {list(VALID_CLASSIFICATION_STATUSES)}"
            )
        return status

    @staticmethod
    def _validate_error_type(error_type: str) -> str:
        if error_type not in VALID_ATTEMPT_ERROR_TYPES:
            raise ValueError(
                f"Invalid attempt error_type: {error_type!r}. "
                f"Must be one of: {list(VALID_ATTEMPT_ERROR_TYPES)}"
            )
        return error_type

    @staticmethod
    def _validate_core_fields(create: ClassificationCreate) -> None:
        """Validate taxonomy-independent fields again at the repository boundary.

        Pydantic validates at construction and (since validate_assignment=True)
        at assignment, but model_copy(update=...) bypasses both. These checks
        cover every field whose vocabulary is fixed, so an invalid value cannot
        be persisted regardless of how the model was produced. Category fields
        are deliberately excluded here: their vocabulary is taxonomy-dependent
        and is enforced at model construction/assignment time via the vibe
        context, never by this repository.
        """
        if create.sentiment not in SENTIMENT_VALUES:
            raise ValueError(
                f"Invalid sentiment: {create.sentiment!r}. Must be one of: {list(SENTIMENT_VALUES)}"
            )
        if create.severity not in SEVERITY_VALUES:
            raise ValueError(
                f"Invalid severity: {create.severity!r}. Must be one of: {list(SEVERITY_VALUES)}"
            )
        if create.confidence is not None and not 0.0 <= create.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {create.confidence!r}")
        if not create.summary or not create.summary.strip():
            raise ValueError("Summary cannot be empty")
        for quote in create.evidence_quotes or []:
            if not isinstance(quote, EvidenceQuote):
                raise ValueError(
                    f"evidence_quotes must contain EvidenceQuote instances, got {type(quote).__name__}"
                )
            if quote.supports not in EvidenceQuote.model_fields["supports"].annotation.__args__:
                raise ValueError(
                    f"Invalid evidence quote supports: {quote.supports!r}. "
                    f"Must be one of: {list(EvidenceQuote.model_fields['supports'].annotation.__args__)}"
                )
            if not quote.quote or not quote.quote.strip():
                raise ValueError("Evidence quote cannot be empty")

    @staticmethod
    def _validate_feedback_product(conn, feedback_id: int, product_id: int) -> int:
        """Verify the feedback record belongs to the supplied product.

        Foreign keys alone cannot catch a (feedback_id, product_id) pair where
        both exist but are unrelated, which would persist a logically
        inconsistent classification or attempt. Raises before any write.

        Returns:
            The product_id actually recorded on the feedback row.
        """
        row = conn.execute(
            "SELECT product_id FROM feedback WHERE feedback_id = ?", (feedback_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Feedback {feedback_id} does not exist")
        if row["product_id"] != product_id:
            raise ValueError(
                f"Feedback {feedback_id} belongs to product {row['product_id']}, "
                f"not product {product_id}: refusing to persist an inconsistent association"
            )
        return row["product_id"]

    def _resolve_product_taxonomy(self, conn, product_id: int) -> tuple:
        """Resolve the Product Vibe taxonomy for a product.

        Uses the existing configuration mechanism (products.vibe_key ->
        load_vibe_config -> ProductVibe.get_primary_categories). No fallback to
        the default SaaS taxonomy: if the product, vibe configuration, or
        taxonomy cannot be resolved, persistence must fail safely.

        Returns:
            (vibe_key, frozenset of valid primary categories)

        Raises:
            ValueError: If the product does not exist, its vibe configuration
                cannot be loaded, or the taxonomy is empty.
        """
        row = conn.execute(
            "SELECT vibe_key FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"Product {product_id} does not exist; cannot resolve its Product Vibe taxonomy"
            )
        vibe_key = row["vibe_key"]

        try:
            vibe = load_vibe_config(vibe_key, self.config_dir)
        except FileNotFoundError as exc:
            raise ValueError(
                f"Cannot resolve Product Vibe '{vibe_key}' for product {product_id}: "
                f"vibe configuration not found ({exc})"
            ) from exc

        categories = frozenset(vibe.get_primary_categories())
        if not categories:
            raise ValueError(
                f"Product Vibe '{vibe_key}' for product {product_id} defines no "
                "primary_categories; refusing to persist classifications against an empty taxonomy"
            )
        return vibe_key, categories

    @staticmethod
    def _validate_categories(
        create: ClassificationCreate, vibe_key: str, product_id: int, valid_categories: frozenset
    ) -> None:
        """Validate primary and secondary categories against the product's taxonomy."""
        if create.primary_category not in valid_categories:
            raise ValueError(
                f"Invalid primary_category {create.primary_category!r} for product "
                f"{product_id} (vibe '{vibe_key}'); must be one of: {sorted(valid_categories)}"
            )
        if create.secondary_category is not None and create.secondary_category not in valid_categories:
            raise ValueError(
                f"Invalid secondary_category {create.secondary_category!r} for product "
                f"{product_id} (vibe '{vibe_key}'); must be one of: {sorted(valid_categories)}"
            )

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _evidence_quotes_to_json(evidence_quotes) -> Optional[str]:
        if evidence_quotes is None:
            return None
        return json.dumps([quote.model_dump() for quote in evidence_quotes])

    @staticmethod
    def _evidence_quotes_from_json(raw: Optional[str]):
        if raw is None:
            return None
        from ..models.classification import EvidenceQuote

        return [EvidenceQuote(**item) for item in json.loads(raw)]

    def _row_to_classification(self, row) -> Classification:
        # model_construct: rows are trusted persisted data that already passed
        # repository validation at write time. Re-running the taxonomy validator
        # here would reject custom-vibe categories because no vibe context is
        # active at read time.
        return Classification.model_construct(
            classification_id=row["classification_id"],
            feedback_id=row["feedback_id"],
            product_id=row["product_id"],
            primary_category=row["primary_category"],
            secondary_category=row["secondary_category"],
            inferred_product_area=row["inferred_product_area"],
            sentiment=row["sentiment"],
            severity=row["severity"],
            customer_intent=row["customer_intent"],
            summary=row["summary"],
            confidence=row["confidence"],
            needs_review=bool(row["needs_review"]),
            evidence_quotes=self._evidence_quotes_from_json(row["evidence_quotes"]),
            classification_reasoning=row["classification_reasoning"],
            mentioned_feature=row["mentioned_feature"],
            is_actionable=None if row["is_actionable"] is None else bool(row["is_actionable"]),
            classification_status=row["classification_status"],
            model_version=row["model_version"],
            model_name=row["model_name"],
            prompt_version=row["prompt_version"],
            error_note=row["error_note"],
            classified_at=datetime.fromisoformat(row["classified_at"]) if row["classified_at"] else datetime.now(),
        )

    def _row_to_attempt(self, row) -> ClassificationAttempt:
        return ClassificationAttempt(
            attempt_id=row["attempt_id"],
            feedback_id=row["feedback_id"],
            product_id=row["product_id"],
            model_name=row["model_name"],
            prompt_version=row["prompt_version"],
            attempt_number=row["attempt_number"],
            error_type=row["error_type"],
            error_detail=row["error_detail"],
            raw_response=row["raw_response"],
            attempted_at=datetime.fromisoformat(row["attempted_at"]) if row["attempted_at"] else datetime.now(),
        )

    # ------------------------------------------------------------------
    # Insert helpers
    # ------------------------------------------------------------------

    _INSERT_SQL = """
        INSERT INTO classifications (
            feedback_id, product_id, primary_category, secondary_category,
            inferred_product_area, sentiment, severity, customer_intent, summary,
            confidence, needs_review, evidence_quotes, classification_reasoning,
            mentioned_feature, is_actionable, classification_status,
            model_version, model_name, prompt_version, error_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    @staticmethod
    def _insert_params(create: ClassificationCreate) -> tuple:
        return (
            create.feedback_id,
            create.product_id,
            create.primary_category,
            create.secondary_category,
            create.inferred_product_area,
            create.sentiment,
            create.severity,
            create.customer_intent,
            create.summary,
            create.confidence,
            create.needs_review,
            ClassificationRepository._evidence_quotes_to_json(create.evidence_quotes),
            create.classification_reasoning,
            create.mentioned_feature,
            create.is_actionable,
            create.classification_status,
            create.model_version,
            create.model_name,
            create.prompt_version,
            create.error_note,
        )

    def _get_by_id(self, conn, classification_id: int) -> Classification:
        row = conn.execute(
            "SELECT * FROM classifications WHERE classification_id = ?", (classification_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Classification {classification_id} not found after insert")
        return self._row_to_classification(row)

    # ------------------------------------------------------------------
    # Classification lifecycle operations
    # ------------------------------------------------------------------

    def insert_classification(self, create: ClassificationCreate) -> Classification:
        """
        Insert a new classification record.

        The create model is Pydantic-validated before it reaches this method;
        the status value is checked again here so the lifecycle vocabulary holds
        even on migrated databases without the schema CHECK constraint.

        Raises:
            ValueError: If classification_status is not 'active' or 'superseded',
                if a taxonomy-independent field is invalid, if the feedback
                does not exist or does not belong to create.product_id, or if
                primary/secondary_category is not in the feedback's product
                vibe taxonomy (or the taxonomy cannot be resolved).
            sqlite3.IntegrityError: On remaining FK violations or when an active
                classification already exists for the feedback record.
        """
        self._validate_status(create.classification_status)
        self._validate_core_fields(create)

        with get_connection(self.db_path) as conn:
            product_id = self._validate_feedback_product(conn, create.feedback_id, create.product_id)
            vibe_key, valid_categories = self._resolve_product_taxonomy(conn, product_id)
            self._validate_categories(create, vibe_key, product_id, valid_categories)
            cursor = conn.execute(self._INSERT_SQL, self._insert_params(create))
            conn.commit()
            return self._get_by_id(conn, cursor.lastrowid)

    def reclassify(self, new: ClassificationCreate) -> Classification:
        """
        Replace the active classification for the feedback with a new one.

        The new classification must already be validated (Pydantic model) and
        carry status 'active'. Within one transaction: the existing active row
        is marked 'superseded' and the new row is inserted as 'active'. If any
        step fails, the transaction rolls back and the previous active
        classification is restored — feedback is never left without its
        previous active classification because of a failed reclassification.

        Raises:
            ValueError: If new.classification_status is not 'active', or if any
                repository-level validation fails (taxonomy-independent fields,
                feedback/product association, or product vibe taxonomy).
            RuntimeError: If the transaction fails (rolled back before raising).
        """
        self._validate_status(new.classification_status)
        if new.classification_status != "active":
            raise ValueError("A reclassification must insert an 'active' classification")

        return self._supersede_and_insert(new)

    def save_human_correction(self, feedback_id: int, correction: ClassificationCreate) -> Classification:
        """
        Persist a human correction as a new active classification.

        The correction is stored with model_name='human', status='active' and
        needs_review cleared; the previous active classification (model or
        human) is marked 'superseded' in the same transaction and preserved as
        history. The supplied feedback_id is validated against the product_id
        on the correction before anything is superseded.

        Raises:
            ValueError: If classification_status is invalid, if a
                taxonomy-independent field is invalid, if the feedback does
                not exist or does not belong to correction.product_id, or if
                the correction's categories are not in the product's vibe
                taxonomy (all before anything is superseded).
        """
        self._validate_status(correction.classification_status)

        corrected = correction.model_copy(update={
            "feedback_id": feedback_id,
            "model_name": "human",
            "classification_status": "active",
            "needs_review": False,
        })
        return self._supersede_and_insert(corrected)

    def _supersede_and_insert(self, new: ClassificationCreate) -> Classification:
        """Supersede the current active row and insert the new active row atomically."""
        self._validate_core_fields(new)

        try:
            with get_connection(self.db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")

                # Consistency and taxonomy checks precede the supersede UPDATE,
                # so an invalid association or category can never modify
                # existing data.
                product_id = self._validate_feedback_product(conn, new.feedback_id, new.product_id)
                vibe_key, valid_categories = self._resolve_product_taxonomy(conn, product_id)
                self._validate_categories(new, vibe_key, product_id, valid_categories)

                conn.execute(
                    "UPDATE classifications SET classification_status = 'superseded' "
                    "WHERE feedback_id = ? AND classification_status = 'active'",
                    (new.feedback_id,),
                )

                cursor = conn.execute(self._INSERT_SQL, self._insert_params(new))
                new_id = cursor.lastrowid

                conn.commit()
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"Classification replacement failed and was rolled back: {exc}"
            ) from exc

        with get_connection(self.db_path) as conn:
            return self._get_by_id(conn, new_id)

    def supersede_classification(self, classification_id: int) -> bool:
        """
        Mark a classification as 'superseded'.

        Only a currently-active row can be superseded; superseded rows are never
        modified again.

        Returns:
            True if a row was superseded, False if the row does not exist or is
            not active.
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE classifications SET classification_status = 'superseded' "
                "WHERE classification_id = ? AND classification_status = 'active'",
                (classification_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_classification(self, classification_id: int) -> Optional[Classification]:
        """Get a classification record by ID."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM classifications WHERE classification_id = ?", (classification_id,)
            ).fetchone()
        return self._row_to_classification(row) if row else None

    def get_active_classification(self, feedback_id: int) -> Optional[Classification]:
        """Get the active classification for a feedback record, if any."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM classifications WHERE feedback_id = ? AND classification_status = 'active'",
                (feedback_id,),
            ).fetchone()
        return self._row_to_classification(row) if row else None

    def get_classification_history(self, feedback_id: int) -> List[Classification]:
        """
        Get all classification records for a feedback record, newest first.

        Never deletes anything; superseded rows remain retrievable here.
        """
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM classifications WHERE feedback_id = ? ORDER BY classification_id DESC",
                (feedback_id,),
            ).fetchall()
        return [self._row_to_classification(row) for row in rows]

    def get_unclassified_feedback_ids(
        self, product_id: int, limit: Optional[int] = None
    ) -> List[int]:
        """
        List feedback IDs for a product that have no active classification.

        A feedback record with only superseded classifications counts as
        unclassified. Ordered by feedback_id for deterministic resumable runs.
        """
        query = """
            SELECT f.feedback_id
            FROM feedback f
            WHERE f.product_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM classifications c
                  WHERE c.feedback_id = f.feedback_id
                    AND c.classification_status = 'active'
              )
            ORDER BY f.feedback_id
        """
        params = (product_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (product_id, limit)

        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [row["feedback_id"] for row in rows]

    def get_product_classifications(
        self, product_id: int, active_only: bool = True
    ) -> List[Classification]:
        """Get classifications for a product, active-only by default."""
        query = "SELECT * FROM classifications WHERE product_id = ?"
        if active_only:
            query += " AND classification_status = 'active'"
        query += " ORDER BY classification_id"

        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, (product_id,)).fetchall()
        return [self._row_to_classification(row) for row in rows]

    # ------------------------------------------------------------------
    # Classification attempts (failures only)
    # ------------------------------------------------------------------

    def record_attempt(
        self,
        feedback_id: int,
        product_id: int,
        attempt_number: int,
        error_type: str,
        error_detail: Optional[str] = None,
        raw_response: Optional[str] = None,
        model_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> int:
        """
        Persist a failed classification attempt in classification_attempts.

        Failed attempts never enter the classifications table, so no invented
        categories, severities or confidences are ever stored. Raw responses
        are truncated to the 8,000-character database limit before insertion.

        Args:
            feedback_id: Feedback the attempt was made for.
            product_id: Associated product ID.
            attempt_number: 1-based attempt counter for this feedback record.
            error_type: One of invalid_json, validation_error, provider_error, timeout.
            error_detail: Failure details (e.g. validation error message).
            raw_response: Raw model output; truncated to 8,000 characters.
            model_name: Model used for the attempt.
            prompt_version: Prompt version used.

        Returns:
            The new attempt_id.

        Raises:
            ValueError: If error_type is not a valid error type, or if the
                feedback does not exist or does not belong to product_id.
            sqlite3.IntegrityError: On remaining FK violations (e.g. unknown product).
        """
        self._validate_error_type(error_type)

        if raw_response is not None and len(raw_response) > MAX_RAW_RESPONSE_LENGTH:
            raw_response = raw_response[:MAX_RAW_RESPONSE_LENGTH]

        with get_connection(self.db_path) as conn:
            self._validate_feedback_product(conn, feedback_id, product_id)
            cursor = conn.execute(
                """
                INSERT INTO classification_attempts (
                    feedback_id, product_id, model_name, prompt_version,
                    attempt_number, error_type, error_detail, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    product_id,
                    model_name,
                    prompt_version,
                    attempt_number,
                    error_type,
                    error_detail,
                    raw_response,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_attempts_for_feedback(self, feedback_id: int) -> List[ClassificationAttempt]:
        """Get all recorded attempts for a feedback record, in attempt order."""
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM classification_attempts WHERE feedback_id = ? ORDER BY attempt_number",
                (feedback_id,),
            ).fetchall()
        return [self._row_to_attempt(row) for row in rows]


# Global repository instance
_repository: Optional[ClassificationRepository] = None


def get_classification_repository(db_path: Optional[Path] = None) -> ClassificationRepository:
    """Get or create the global classification repository."""
    global _repository
    if _repository is None:
        _repository = ClassificationRepository(db_path)
    return _repository
