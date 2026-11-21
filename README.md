# ProductSignal

**AI-Powered Customer Feedback Intelligence & Product Discovery Platform**

Transform unstructured customer feedback into structured product insights and actionable product decisions.

## Overview

ProductSignal helps product teams move from thousands of customer comments to a prioritized, evidence-backed product roadmap.

**Core Workflow:**
```
Customer Feedback → Problem Discovery → Evidence → Prioritization → Opportunity Brief → Experiment → PRD
```

## Implementation Status

### Implemented (Phase 1 Foundation)

- **Product Context Setup** — Define product type, category, target customers, and use case
- **SaaS Product Vibe** — Configurable analytical lens for SaaS products (config/vibes/saas.yaml)
- **SQLite Foundation** — 10-table schema with foreign keys, WAL mode, cascade deletes
- **Pydantic Models** — FeedbackRecord, Classification with validation
- **Product CRUD** — Create, read, update, delete, list products; explicit active product flag
- **Basic Streamlit Application** — Home page with project selection/creation, sidebar status
- **External ID Uniqueness** — Database-level constraint preventing re-imports per product
- **Content Hash Normalization** — Deterministic SHA-256 from normalized text
- **Configuration Loading** — CWD-independent paths anchored to project root
- **Product Vibe Cache** — Cache keys include resolved config directory
- **Configurable Classification Taxonomy** — Validation uses active vibe or explicit taxonomy
- **Test Suite** — 100+ tests covering models, database, config, product context, app

### Implemented (Phase 2.1-2.3 — Feedback Ingestion)

- **CSV Feedback Ingestion** — Upload, validation, preview, and import for the **Kaggle Customer Support Tickets schema only**
- **Feedback Text Construction** — Combines Ticket Subject and Ticket Description with placeholder replacement
- **External ID Namespacing** — Namespaced IDs (`kaggle_support:{Ticket ID}`) to prevent cross-dataset collisions
- **Timestamp Handling** — First Response Time used as proxy for creation time (NULL when missing; no fallback to Date of Purchase)
- **Rating Validation** — Only integer-valued 1-5 ratings accepted; fractional values rejected and set to NULL
- **Original Category Construction** — Combines Ticket Type and Ticket Subject
- **PII Exclusion** — Customer Name, Email, Age, Gender are never persisted
- **Duplicate Import Prevention** — Database-level unique constraint on (product_id, external_id)
- **Repeated Content Preservation** — Content hashes computed for detection only; repeated feedback is never deduplicated
- **Atomic Import Transactions** — Single database transaction; unexpected failures roll back entire import
- **Preview & Validation** — Schema validation, data quality metrics, sample records, column mapping display
- **Temporary File Cleanup** — Uploaded CSVs cleaned up after processing; PII in uploads never persists
- **Streamlit Ingestion Page** — Interactive upload, preview, validation, and import workflow

### Planned (Phase 2.4+)

- **AI Classification** — LLM-powered feedback classification (12 SaaS categories)
- **Semantic Clustering** — Embedding-based grouping of similar feedback
- **Opportunity Scoring** — Transparent prioritization (frequency, severity, segment impact, recency, business relevance)
- **Opportunity Briefs** — Evidence-backed product opportunity documents
- **Experiment Hypotheses** — Testable product hypotheses from opportunities
- **Draft PRD Generation** — Editable product requirement documents
- **Integrations** — Zendesk, Intercom, Jira, Linear, App Store, Google Play

> **Note:** The current ingestion implementation supports the validated Kaggle Customer Support Tickets schema only. Generic user-defined column mapping is **not implemented** and remains planned functionality. The dataset is synthetic and intended for pipeline testing, not genuine SaaS model evaluation.

## Technology Stack

- **Frontend:** Streamlit
- **Backend:** Python 3.12+
- **Database:** SQLite (WAL mode, foreign keys enabled)
- **Validation:** Pydantic 2
- **Data Processing:** Pandas
- **Configuration:** PyYAML
- **ML/AI:** Sentence Transformers, scikit-learn (for embeddings/clustering — Phase 2)
- **LLM:** Ollama (local) — Qwen models (Phase 2)
- **Testing:** Pytest

## Project Structure

```
ProductSignal/
├── config/
│   └── vibes/
│       └── saas.yaml          # SaaS Product Vibe configuration
├── data/
│   ├── raw/                   # Raw CSV feedback data
│   └── .gitkeep
├── docs/
│   ├── ProductSignal_PRD.md   # PRD v1
│   └── ProductSignal_PRD_V2.md # PRD v2 (approved)
├── src/
│   └── productsignal/
│       ├── __init__.py
│       ├── config.py          # Configuration & Product Vibe loading
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py  # Database connection management
│       │   └── schema.sql     # Database schema (10 tables)
│       ├── models/
│       │   ├── __init__.py
│       │   ├── feedback.py    # Feedback data models
│       │   └── classification.py # Classification data models
│       ├── product_context/
│       │   ├── __init__.py
│       │   └── repository.py  # Product CRUD operations
│       └── app/
│           ├── __init__.py
│           └── Home.py        # Streamlit application entry point
├── tests/
│   ├── conftest.py
│   ├── test_app_smoke.py
│   ├── test_classification_model.py
│   ├── test_config_vibe.py
│   ├── test_database.py
│   ├── test_feedback_model.py
│   └── test_product_context.py
├── scripts/
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.12+
- Git

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd ProductSignal

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (automatic on first run)
# No manual step needed - happens on first app launch
```

### Running the Application

```bash
# Activate virtual environment
source .venv/bin/activate

# Run Streamlit app
streamlit run src/productsignal/app/Home.py
```

The app will be available at `http://localhost:8501`

### Running Tests

```bash
# Run all tests from repository root
pytest tests/ -v

# Run from any directory (CWD-independent)
cd /tmp && pytest /absolute/path/to/ProductSignal/tests/ -v

# Run with coverage
pytest tests/ --cov=src/productsignal --cov-report=html
```

## Configuration

### Product Vibe (config/vibes/saas.yaml)

The SaaS Product Vibe defines:
- **Analytical focus areas** (workflow_efficiency, reliability, feature_adoption, etc.)
- **Classification taxonomy** (12 primary categories)
- **Scoring weights** (frequency: 25%, severity: 25%, segment_impact: 20%, recency: 10%, business_relevance: 20%)
- **Analytical questions** for problem discovery, reliability, adoption, and business impact
- **Evidence guardrails** for traceability
- **Clustering and classification parameters**

### Database

SQLite database stored at `data/productsignal.db` with 10 tables:
- `products` — Product configuration (with explicit `is_active` flag)
- `feedback` — Original customer feedback (never overwritten; `external_id` unique per product)
- `classifications` — AI-generated classifications
- `clusters` — Problem clusters
- `cluster_feedback` — Cluster-feedback mappings
- `opportunities` — Prioritized opportunities
- `opportunity_evidence` — Evidence linking
- `briefs` — Opportunity briefs
- `experiments` — Experiment hypotheses
- `prds` — Product requirement documents

## Architecture Principles

1. **Separation of Concerns** — AI for language understanding, deterministic Python for calculations/validation
2. **Evidence Traceability** — Every claim links to source feedback
3. **Human-in-the-Loop** — AI generates, humans approve
4. **Local-First** — No paid APIs required for MVP
5. **Extensible** — Product Vibe system enables multiple product types

## Database Migration Policy (Pre-Release)

This project is in pre-release (Phase 1 Foundation). The following policy applies to database schema changes:

1. **No guaranteed automatic upgrades** — Pre-release database schemas are not guaranteed to support automatic upgrades. Schema changes may require database reinitialization.

2. **Explicit reinitialization before real data** — Before persistent customer feedback data is introduced, the database must be explicitly reinitialized to the current schema. The `initialize_database()` function in `src/productsignal/db/connection.py` creates the schema from `schema.sql`.

3. **Never silently delete or overwrite** — The application will not silently delete or overwrite an existing database file. If a database exists at the configured path, `initialize_database()` will execute the schema (which uses `CREATE TABLE IF NOT EXISTS`), but schema changes that require `ALTER TABLE` or `DROP TABLE` are not performed automatically.

4. **Migration and backup procedures required before real data** — Before any database containing real customer feedback is used, proper migration scripts and backup procedures must be implemented. This is a prerequisite for moving beyond Phase 1.

5. **Explicit decision for existing data** — Any existing database containing real feedback requires an explicit migration or backup decision by the operator. The current Phase 1 code does not make this decision automatically.

**Current behavior:** `initialize_database()` is idempotent for `CREATE TABLE IF NOT EXISTS` statements. It will add missing tables but will not modify existing table structures (e.g., add/remove columns, change constraints). For schema changes that require structural modifications, the database must be recreated.

## Development Roadmap (Implementation Sequence Derived from PRD V2)

The following represents the planned implementation/build sequence derived from the PRD V2 requirements.
Note: Phase numbering here reflects implementation order and does not directly correspond to the PRD V2's strategic phase numbering (which begins at Phase 2 for post-MVP work).

- **Step 1 (Current - Phase 1 Foundation):** Foundation — Product Context, Vibe Config, SQLite Schema, Models, CRUD, Basic App
- **Step 2:** Ingestion & Classification — CSV upload, AI classification, semantic clustering
- **Step 3:** Intelligence & Outputs — Opportunity scoring, briefs, experiments, PRDs
- **Step 4:** Integrations — Zendesk, Intercom, Jira, Linear, App Store, Google Play
- **Step 5:** Advanced Intelligence — Trends, segment comparisons, release impact
- **Step 6:** Collaboration — Workspaces, approval workflows, roadmap integrations

See [ProductSignal_PRD_V2.md](docs/ProductSignal_PRD_V2.md) for the full product requirements and strategic roadmap.

## License

This project does not currently include a LICENSE file. License terms to be determined.

## Portfolio Positioning

**AI Product Management | Product Discovery | Customer Intelligence | AI Workflow Design | Product Strategy | Product Analytics**

---

*Do not claim business impact, model accuracy, or time savings until those outcomes have been measured through actual tests.*