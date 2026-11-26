-- ProductSignal Database Schema
-- SQLite with foreign key constraints enabled

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Enable WAL mode for better concurrency
PRAGMA journal_mode = WAL;

-- ============================================================
-- products table: Product configuration and context
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (product_type IN ('service_based', 'consumer_facing')),
    category TEXT NOT NULL,
    target_customers TEXT,
    primary_use_case TEXT,
    key_features TEXT,  -- JSON array stored as TEXT
    description TEXT,
    vibe_key TEXT NOT NULL,  -- References config/vibes/{vibe_key}.yaml
    is_active BOOLEAN DEFAULT FALSE,  -- Explicit active product flag (F3)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for product lookups
CREATE INDEX IF NOT EXISTS idx_products_vibe_key ON products(vibe_key);
CREATE INDEX IF NOT EXISTS idx_products_created_at ON products(created_at);
CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active);

-- Only one product can be active at a time (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS uq_products_active ON products(is_active) WHERE is_active = 1;

-- ============================================================
-- feedback table: Original customer feedback (never overwritten)
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    external_id TEXT,  -- Original identifier from source system
    content_hash TEXT NOT NULL,  -- Hash of feedback_text for duplicate detection
    feedback_text TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMP,  -- Original feedback date
    customer_segment TEXT,
    product_area TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    original_category TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Indexes for feedback queries
CREATE INDEX IF NOT EXISTS idx_feedback_product_id ON feedback(product_id);
CREATE INDEX IF NOT EXISTS idx_feedback_content_hash ON feedback(content_hash);
CREATE INDEX IF NOT EXISTS idx_feedback_external_id ON feedback(external_id);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_source ON feedback(source);

-- Unique constraint on (product_id, external_id) where external_id is not null
-- This prevents accidental re-imports of the same external ID for the same product
-- while allowing multiple NULL external_ids and preserving repeated feedback
CREATE UNIQUE INDEX IF NOT EXISTS uq_feedback_product_external_id 
ON feedback(product_id, external_id) 
WHERE external_id IS NOT NULL;

-- ============================================================
-- classifications table: AI-generated feedback classifications
-- ============================================================
CREATE TABLE IF NOT EXISTS classifications (
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
    -- Phase 3.1 classification extensions
    evidence_quotes TEXT,  -- JSON [{quote, supports}]; verbatim quotes from feedback.feedback_text
    classification_reasoning TEXT,  -- model explanation; audit trail, never treated as evidence
    mentioned_feature TEXT,
    is_actionable BOOLEAN,
    classification_status TEXT NOT NULL DEFAULT 'active'
        CHECK (classification_status IN ('active', 'superseded')),
    model_name TEXT,  -- 'qwen2.5:7b' | 'human' | 'deterministic'
    prompt_version TEXT,  -- e.g. 'cls-v1'
    error_note TEXT,  -- set only when a reclassification attempt failed (see lifecycle design)
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Indexes for classification queries
CREATE INDEX IF NOT EXISTS idx_classifications_feedback_id ON classifications(feedback_id);
CREATE INDEX IF NOT EXISTS idx_classifications_product_id ON classifications(product_id);
CREATE INDEX IF NOT EXISTS idx_classifications_primary_category ON classifications(primary_category);
CREATE INDEX IF NOT EXISTS idx_classifications_needs_review ON classifications(needs_review);

-- NOTE: uq_classifications_active (partial unique index enforcing at most one ACTIVE
-- classification per feedback) is intentionally NOT created here. On databases created
-- before Phase 3.1 the classification_status column does not exist when this script
-- runs, so creating the index at this point would fail. It is created idempotently by
-- initialize_database() in db/connection.py, after missing columns are added and
-- duplicate active rows are deduplicated.

-- ============================================================
-- classification_attempts table: Audit log of failed classification attempts
-- Successful classifications live in `classifications`; every failed LLM call
-- or validation failure is recorded here for forensics and retries.
-- ============================================================
CREATE TABLE IF NOT EXISTS classification_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    model_name TEXT,
    prompt_version TEXT,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    error_type TEXT CHECK (error_type IN ('invalid_json', 'validation_error', 'provider_error', 'timeout')),
    error_detail TEXT,
    raw_response TEXT CHECK (raw_response IS NULL OR length(raw_response) <= 8000),  -- caller truncates before insert
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Indexes for classification attempt queries
CREATE INDEX IF NOT EXISTS idx_classification_attempts_feedback_id ON classification_attempts(feedback_id);
CREATE INDEX IF NOT EXISTS idx_classification_attempts_product_id ON classification_attempts(product_id);

-- ============================================================
-- clusters table: Identified customer problem groups
-- ============================================================
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    problem_title TEXT NOT NULL,
    problem_description TEXT,
    feedback_count INTEGER DEFAULT 0,
    source_distribution TEXT,  -- JSON stored as TEXT
    segment_distribution TEXT,  -- JSON stored as TEXT
    first_observed_at TIMESTAMP,
    last_observed_at TIMESTAMP,
    related_product_areas TEXT,  -- JSON array stored as TEXT
    cluster_confidence REAL CHECK (cluster_confidence >= 0.0 AND cluster_confidence <= 1.0),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'merged', 'split', 'archived')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Indexes for cluster queries
CREATE INDEX IF NOT EXISTS idx_clusters_product_id ON clusters(product_id);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON clusters(status);

-- ============================================================
-- cluster_feedback table: Many-to-many mapping between clusters and feedback
-- ============================================================
CREATE TABLE IF NOT EXISTS cluster_feedback (
    cluster_id INTEGER NOT NULL,
    feedback_id INTEGER NOT NULL,
    similarity_score REAL CHECK (similarity_score >= 0.0 AND similarity_score <= 1.0),
    is_representative BOOLEAN DEFAULT FALSE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cluster_id, feedback_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE
);

-- Index for cluster_feedback queries
CREATE INDEX IF NOT EXISTS idx_cluster_feedback_feedback_id ON cluster_feedback(feedback_id);
CREATE INDEX IF NOT EXISTS idx_cluster_feedback_representative ON cluster_feedback(is_representative);

-- ============================================================
-- opportunities table: Prioritized product opportunities
-- ============================================================
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    opportunity_score REAL CHECK (opportunity_score >= 0.0 AND opportunity_score <= 100.0),
    frequency_score INTEGER CHECK (frequency_score >= 1 AND frequency_score <= 5),
    severity_score INTEGER CHECK (severity_score >= 1 AND severity_score <= 5),
    segment_impact_score INTEGER CHECK (segment_impact_score >= 1 AND segment_impact_score <= 5),
    recency_score INTEGER CHECK (recency_score >= 1 AND recency_score <= 5),
    business_relevance_score INTEGER CHECK (business_relevance_score >= 1 AND business_relevance_score <= 5),
    scoring_weights TEXT,  -- JSON stored as TEXT
    scoring_rationale TEXT,  -- Explanation of scores
    missing_information TEXT,  -- JSON array of missing data points
    status TEXT DEFAULT 'identified' CHECK (status IN ('identified', 'reviewed', 'approved', 'rejected', 'archived')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id) ON DELETE CASCADE
);

-- Indexes for opportunity queries
CREATE INDEX IF NOT EXISTS idx_opportunities_product_id ON opportunities(product_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_cluster_id ON opportunities(cluster_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(opportunity_score DESC);

-- ============================================================
-- opportunity_evidence table: Evidence supporting opportunities
-- ============================================================
CREATE TABLE IF NOT EXISTS opportunity_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL,
    feedback_id INTEGER NOT NULL,
    evidence_type TEXT CHECK (evidence_type IN ('direct_quote', 'aggregated_statistic', 'pattern_observation')),
    relevance_score REAL CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE
);

-- Index for evidence queries
CREATE INDEX IF NOT EXISTS idx_opportunity_evidence_opportunity_id ON opportunity_evidence(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_evidence_feedback_id ON opportunity_evidence(feedback_id);

-- ============================================================
-- briefs table: Generated opportunity briefs
-- ============================================================
CREATE TABLE IF NOT EXISTS briefs (
    brief_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    problem_statement TEXT,
    customer_impact TEXT,
    evidence_summary TEXT,
    affected_segments TEXT,  -- JSON stored as TEXT
    frequency_and_severity TEXT,
    existing_limitations TEXT,
    potential_opportunities TEXT,
    risks_and_assumptions TEXT,
    recommended_investigation TEXT,
    suggested_next_steps TEXT,
    evidence_references TEXT,  -- JSON array of feedback_ids
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'approved', 'archived')),
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Index for brief queries
CREATE INDEX IF NOT EXISTS idx_briefs_opportunity_id ON briefs(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_briefs_product_id ON briefs(product_id);
CREATE INDEX IF NOT EXISTS idx_briefs_status ON briefs(status);

-- ============================================================
-- experiments table: Generated experiment hypotheses
-- ============================================================
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    problem_statement TEXT,
    hypothesis TEXT,
    target_segment TEXT,
    primary_metric TEXT,
    secondary_metrics TEXT,  -- JSON array stored as TEXT
    test_approach TEXT,
    guardrail_metrics TEXT,  -- JSON array stored as TEXT
    status TEXT DEFAULT 'proposed' CHECK (status IN ('proposed', 'designed', 'running', 'completed', 'archived')),
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (brief_id) REFERENCES briefs(brief_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Index for experiment queries
CREATE INDEX IF NOT EXISTS idx_experiments_brief_id ON experiments(brief_id);
CREATE INDEX IF NOT EXISTS idx_experiments_product_id ON experiments(product_id);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);

-- ============================================================
-- prds table: Generated product requirement documents
-- ============================================================
CREATE TABLE IF NOT EXISTS prds (
    prd_id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    problem_statement TEXT,
    product_context TEXT,
    user_personas TEXT,  -- JSON stored as TEXT
    goals_and_non_goals TEXT,
    user_stories TEXT,  -- JSON array stored as TEXT
    functional_requirements TEXT,  -- JSON array stored as TEXT
    acceptance_criteria TEXT,  -- JSON array stored as TEXT
    success_metrics TEXT,  -- JSON array stored as TEXT
    risks_and_dependencies TEXT,
    open_questions TEXT,  -- JSON array stored as TEXT
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'approved', 'exported', 'archived')),
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Index for PRD queries
CREATE INDEX IF NOT EXISTS idx_prds_experiment_id ON prds(experiment_id);
CREATE INDEX IF NOT EXISTS idx_prds_product_id ON prds(product_id);
CREATE INDEX IF NOT EXISTS idx_prds_status ON prds(status);

-- ============================================================
-- Trigger to update updated_at timestamps
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_products_timestamp
AFTER UPDATE ON products
BEGIN
    UPDATE products SET updated_at = CURRENT_TIMESTAMP WHERE product_id = NEW.product_id;
END;

CREATE TRIGGER IF NOT EXISTS update_clusters_timestamp
AFTER UPDATE ON clusters
BEGIN
    UPDATE clusters SET updated_at = CURRENT_TIMESTAMP WHERE cluster_id = NEW.cluster_id;
END;

CREATE TRIGGER IF NOT EXISTS update_opportunities_timestamp
AFTER UPDATE ON opportunities
BEGIN
    UPDATE opportunities SET updated_at = CURRENT_TIMESTAMP WHERE opportunity_id = NEW.opportunity_id;
END;

CREATE TRIGGER IF NOT EXISTS update_briefs_timestamp
AFTER UPDATE ON briefs
BEGIN
    UPDATE briefs SET updated_at = CURRENT_TIMESTAMP WHERE brief_id = NEW.brief_id;
END;

CREATE TRIGGER IF NOT EXISTS update_experiments_timestamp
AFTER UPDATE ON experiments
BEGIN
    UPDATE experiments SET updated_at = CURRENT_TIMESTAMP WHERE experiment_id = NEW.experiment_id;
END;

CREATE TRIGGER IF NOT EXISTS update_prds_timestamp
AFTER UPDATE ON prds
BEGIN
    UPDATE prds SET updated_at = CURRENT_TIMESTAMP WHERE prd_id = NEW.prd_id;
END;