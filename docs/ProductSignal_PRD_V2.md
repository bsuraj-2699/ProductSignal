# ProductSignal

## AI-Powered Customer Feedback Intelligence & Product Discovery Platform

**Document:** Final Product Requirements Document\
**Version:** 2.0\
**Status:** Final --- Approved for MVP Development\
**MVP Target:** 7-day build\
**Initial Product Configuration:** Service-based → SaaS\
**Primary Users:** Product Managers, Product Analysts, Product
Operations Teams

------------------------------------------------------------------------

# 1. Executive Summary

## 1.1 Product Overview

ProductSignal is an AI-powered customer feedback intelligence platform
that transforms unstructured customer feedback into structured product
insights and actionable product decisions.

Product teams receive feedback from multiple sources, including customer
support tickets, application reviews, surveys, interviews and feature
requests. However, this feedback is often fragmented, repetitive and
difficult to translate into product priorities.

ProductSignal addresses this problem by combining AI-powered feedback
analysis, semantic clustering, evidence-backed opportunity
prioritization and product document generation.

Its central workflow is:

**Customer Feedback → Problem Discovery → Evidence → Prioritization →
Opportunity Brief → Experiment → PRD**

## 1.2 Core Value Proposition

Help product teams move from thousands of customer comments to a
prioritized, evidence-backed product roadmap.

## 1.3 Product Vision

Become a product intelligence layer between customer feedback and
product strategy.

ProductSignal should help product teams understand:

1.  What problems are customers repeatedly experiencing?
2.  Which problems deserve product attention first?
3.  What evidence supports those decisions?
4.  What should the product team investigate or build next?

------------------------------------------------------------------------

# 2. Problem Statement

Product teams encounter five major challenges:

### Fragmented feedback

Customer feedback exists across support systems, application reviews,
surveys, interviews and other platforms.

### Repetitive information

Different customers describe the same underlying problem in different
ways.

### Difficult prioritization

Product teams struggle to distinguish frequent, high-impact problems
from isolated feature requests.

### Limited evidence

Product decisions can be driven by individual stakeholder opinions
instead of aggregated customer evidence.

### Manual product discovery

Converting customer feedback into opportunity briefs, experiments and
PRDs takes significant time.

ProductSignal aims to reduce these problems through an integrated
feedback intelligence workflow.

------------------------------------------------------------------------

# 3. Target Users

## 3.1 Primary Persona: Product Manager

**Responsibilities** - Understand customer problems. - Prioritize
product improvements. - Coordinate with engineering and design teams. -
Maintain product roadmaps. - Evaluate product opportunities.

**Pain points** - Too much customer feedback. - Difficulty identifying
recurring problems. - Lack of evidence behind feature requests. -
Stakeholder pressure to prioritize individual opinions. - Manual
preparation of product documents.

**Desired outcome:** Faster and more defensible product decisions.

## 3.2 Secondary Persona: Product Operations Analyst

**Responsibilities** - Collect customer feedback. - Maintain customer
insight repositories. - Identify recurring issues. - Prepare product
reports. - Support product prioritization.

**Desired outcome:** Automate repetitive feedback analysis and generate
reliable product insights.

------------------------------------------------------------------------

# 4. Product Context and Product Vibe

This is a core product capability and a major part of ProductSignal's
differentiation.

## 4.1 Product Context Setup

Before analysing feedback, users must create a product project and
provide its context.

The context allows ProductSignal to understand what kind of product is
being analysed, who uses it and what problems matter to those users.

### Required project information

  Field                 Description                        Requirement
  --------------------- ---------------------------------- -------------
  Product name          Name of the product                Required
  Product type          Service-based or consumer-facing   Required
  Product category      SaaS, fintech, mobile app, etc.    Required
  Target customers      Intended customer segments         Required
  Primary use case      Main purpose of the product        Required
  Key features          Important product capabilities     Optional
  Product description   Additional product context         Optional

### Example: Initial SaaS configuration

  -----------------------------------------------------------------------
  Field                               Example
  ----------------------------------- -----------------------------------
  Product name                        FlowDesk

  Product type                        Service-based

  Category                            SaaS --- Project Management

  Target customers                    Small and medium businesses

  Primary use case                    Project collaboration and task
                                      management

  Key features                        Task assignment, reporting,
                                      automation and integrations
  -----------------------------------------------------------------------

The example product is fictional and used for demonstration.

## 4.2 Product Types

ProductSignal will eventually support two broad product types.

### A. Service-based products

Products where users primarily consume a service or complete a
service-driven workflow.

Examples: - SaaS platforms. - Enterprise software. - Fintech and banking
platforms. - CRM and HR platforms. - AI-powered services.

### B. Consumer-facing products

Products used directly in everyday life, where convenience, usability
and real-world customer experience are important.

Examples: - Mobile applications. - E-commerce platforms. - Food delivery
services. - Streaming applications. - Consumer devices and digital
products.

**MVP limitation:** Only service-based SaaS analysis will be fully
implemented. Consumer-facing analysis will be part of the future
roadmap.

## 4.3 Product Vibe

Product Vibe is ProductSignal's context-aware analytical configuration.

It changes how the AI interprets customer feedback, identifies problems,
prioritizes opportunities and generates recommendations.

It does not change the underlying customer evidence.

### SaaS Product Vibe

For SaaS products, the analytical lens focuses on:

-   Workflow efficiency.
-   Platform reliability.
-   Feature adoption.
-   User onboarding.
-   Customer retention.
-   Integration performance.
-   Business value.
-   Productivity.

### Future Consumer Product Vibe

For consumer-facing products, the analytical lens will focus on:

-   Usability.
-   Convenience.
-   Accessibility.
-   Customer satisfaction.
-   User experience.
-   Repeat usage.
-   Purchase friction.
-   Product performance.

## 4.4 Product Vibe Architecture

ProductSignal must use a shared intelligence engine with configurable
analytical perspectives.

**Architecture principle:**

One intelligence engine. Multiple product perspectives.

The selected product context influences:

1.  Classification instructions.
2.  Problem categorization.
3.  Clustering interpretation.
4.  Opportunity scoring.
5.  Opportunity brief generation.
6.  Experiment recommendations.
7.  PRD generation.

Product Vibe must not fabricate customer context or modify original
feedback.

------------------------------------------------------------------------

# 5. Product Goals and Non-Goals

## 5.1 Product Goals

1.  Reduce manual effort required to analyse customer feedback.
2.  Identify recurring customer problems across feedback sources.
3.  Group related feedback into meaningful problem clusters.
4.  Provide transparent opportunity prioritization.
5.  Generate evidence-backed opportunity briefs.
6.  Convert opportunities into experiment hypotheses and draft PRDs.
7.  Establish a flexible architecture for multiple product categories.

## 5.2 Non-Goals

The MVP will not:

-   Replace Jira, Linear or Productboard.
-   Automatically make roadmap decisions.
-   Provide real-time integrations with every feedback platform.
-   Predict actual revenue impact without supporting data.
-   Function as a general-purpose chatbot.
-   Generate fully autonomous product roadmaps.
-   Support cross-product portfolio benchmarking.
-   Claim that customer feedback alone proves churn or revenue impact.

------------------------------------------------------------------------

# 6. MVP Functional Requirements

## Feature 1: Product Context Setup

**Description:** Allow users to create a product project and define its
context before feedback analysis.

### Requirements

-   Product name input.
-   Product type selection.
-   Product category selection.
-   Target customer input.
-   Primary use case input.
-   Optional product description and key features.
-   Save project configuration.
-   Display active Product Vibe.

### Acceptance Criteria

-   Users can create a SaaS product project.
-   Product context is saved in the database.
-   Analysis uses the saved product context.
-   Users can inspect the active configuration.
-   Product context can be edited.

**Priority:** P0

## Feature 2: Feedback Ingestion

**Description:** Allow users to import customer feedback from CSV files.

### Initial data sources

-   Customer support tickets.
-   Google Play or App Store reviews.
-   Customer surveys.
-   Feature requests.
-   Product feedback records.

### Standard feedback schema

  Field               Description
  ------------------- ---------------------------------
  feedback_id         Unique feedback identifier
  feedback_text       Original customer feedback
  source              Original feedback channel
  created_at          Feedback date
  customer_segment    Customer segment, if available
  product_area        Product area, if available
  rating              Customer rating, if available
  original_category   Original category, if available

### Requirements

-   CSV upload.
-   Column mapping.
-   Schema validation.
-   Duplicate detection.
-   Missing-field handling.
-   Preview before importing.
-   Original data preservation.
-   Import error reporting.

Where metadata is unavailable, fields must remain null or be explicitly
marked as AI-inferred. ProductSignal must not invent original metadata.

### Acceptance Criteria

-   Valid CSV files can be uploaded.
-   Users can preview records before importing.
-   Invalid rows are identified.
-   Imported feedback is stored.
-   Original feedback text is preserved.

**Priority:** P0

## Feature 3: AI Feedback Classification

**Description:** Classify individual feedback records using an LLM and
the selected Product Vibe.

### SaaS classification taxonomy

Initial categories:

1.  Reliability and downtime.
2.  Performance and speed.
3.  Workflow efficiency.
4.  Feature usability.
5.  User onboarding.
6.  Integration issues.
7.  Reporting and analytics.
8.  Data accuracy and integrity.
9.  Feature requests.
10. Pricing and value.
11. Customer support.
12. Other / unclear.

### Classification output

Each feedback record should contain:

-   Primary problem category.
-   Secondary category, if applicable.
-   Product area.
-   Sentiment or emotional tone.
-   Problem severity.
-   Customer intent.
-   Short summary.
-   Confidence or uncertainty indicator.
-   Evidence reference to the original feedback.

### Requirements

-   Structured JSON output.
-   Pydantic validation.
-   Retry handling for malformed outputs.
-   Original and AI-generated data stored separately.
-   Uncertain classifications flagged for review.
-   Product context supplied to the LLM.
-   Batch processing support.

### Acceptance Criteria

-   Feedback is classified using a consistent schema.
-   Invalid outputs are rejected or retried.
-   Original feedback remains accessible.
-   Uncertain results are visibly flagged.
-   Classifications are evaluated against a manually labelled sample.

**Priority:** P0

## Feature 4: Problem Clustering

**Description:** Identify recurring customer problems across feedback
records.

### Example

  Original feedback                   Identified problem
  ----------------------------------- ----------------------
  Dashboard takes too long to load    Platform performance
  Reports are extremely slow          Platform performance
  Analytics page freezes frequently   Platform performance

### Cluster output

Each cluster should contain:

-   Problem title.
-   Problem description.
-   Number of related feedback records.
-   Representative customer comments.
-   Feedback source distribution.
-   Affected customer segments.
-   First and most recent observed dates.
-   Related product areas.
-   Cluster confidence or quality indicator.

### Requirements

-   Semantic embeddings.
-   Similarity-based grouping.
-   Configurable similarity threshold.
-   Representative feedback selection.
-   Manual correction of cluster assignments.
-   Access to original evidence.

### Acceptance Criteria

-   Similar feedback can be grouped together.
-   Users can inspect cluster evidence.
-   Incorrectly grouped records can be corrected.
-   The system does not invent feedback records.

**Priority:** P0

## Feature 5: Opportunity Prioritization

**Description:** Rank identified problem clusters using a transparent
scoring framework.

### SaaS prioritization framework

  Dimension                   Weight
  ------------------------- --------
  Frequency                      25%
  Severity                       25%
  Customer segment impact        20%
  Recency                        10%
  Business relevance             20%

Each dimension receives a score between 1 and 5.

### Scoring formula

Weighted score = Sum of (dimension score × dimension weight)

Normalized score:

Opportunity Score = Weighted Score × 20

The final score ranges from 20 to 100 under this five-point scale.

### Example

  Dimension              Score   Weight
  -------------------- ------- --------
  Frequency                  5      25%
  Severity                   4      25%
  Segment impact             4      20%
  Recency                    5      10%
  Business relevance         3      20%

The final score is calculated by deterministic Python logic.

### Requirements

-   Calculate frequency from actual feedback counts.
-   Estimate severity using classified feedback.
-   Assess segment impact using available customer metadata.
-   Calculate recency from feedback dates.
-   Recommend business relevance using available product context.
-   Show the individual dimension scores.
-   Explain scoring assumptions.
-   Allow manual review.
-   Clearly identify missing information.

**Important:** The LLM may recommend scores and provide explanations.
The application calculates the final score. Missing evidence must not be
silently converted into high scores.

### Acceptance Criteria

-   Scores are reproducible.
-   Users can inspect score components.
-   Missing data is clearly disclosed.
-   Every opportunity can be traced to supporting feedback.

**Priority:** P0

## Feature 6: Opportunity Brief Generator

**Description:** Generate an evidence-backed product opportunity brief
from a selected problem cluster.

### Output structure

1.  Problem statement.
2.  Customer impact.
3.  Evidence summary.
4.  Affected customer segments.
5.  Frequency and severity.
6.  Existing limitations.
7.  Potential product opportunities.
8.  Risks and assumptions.
9.  Recommended investigation.
10. Suggested next steps.

Every factual claim must link to supporting feedback records.

### Acceptance Criteria

-   Briefs are generated from selected clusters.
-   Evidence references are retained.
-   Hypotheses and facts are clearly distinguished.
-   Users can review the generated content.

**Priority:** P0

## Feature 7: Experiment Hypothesis Generator

**Description:** Convert a reviewed product opportunity into a testable
experiment hypothesis.

### Example

**Problem:** Customers struggle with automation configuration.

**Hypothesis:** If we simplify the automation setup experience and
introduce guided configuration, users will complete automation setup
more successfully.

**Suggested experiment:**

-   Target segment: New SaaS customers.
-   Primary metric: Automation setup completion rate.
-   Secondary metric: Automation-related support tickets.
-   Test approach: Controlled rollout or A/B test.
-   Guardrail: Time required to complete setup.

The system must distinguish suggested metrics from actual measured
results.

**Priority:** P1

## Feature 8: Draft PRD Generator

**Description:** Convert an approved opportunity into an editable
product requirements document.

### Generated sections

-   Problem statement.
-   Product context.
-   User personas.
-   Goals and non-goals.
-   User stories.
-   Functional requirements.
-   Acceptance criteria.
-   Success metrics.
-   Risks and dependencies.
-   Open questions.

PRD generation must use the saved product context and approved
opportunity brief.

**Priority:** P1

## Feature 9: Product Vibe Configuration

**Description:** Apply product-specific analytical configurations to the
shared intelligence engine.

### MVP behaviour

-   Support service-based products.
-   Support SaaS as the initial category.
-   Apply SaaS-specific classification taxonomy.
-   Apply SaaS-specific analytical questions.
-   Apply SaaS scoring weights.
-   Adapt opportunity briefs and experiment suggestions.
-   Preserve original feedback and evidence.

### Future behaviour

-   Consumer-facing product configuration.
-   Additional product categories.
-   Custom analytical lenses.
-   User-defined scoring weights.
-   Multiple product projects.
-   Cross-product comparisons.

**Priority:** P0 for SaaS configuration; P2 for additional product
types.

------------------------------------------------------------------------

# 7. SaaS Product Analysis Framework

ProductSignal must use a consistent set of analytical questions to
interpret feedback.

The same underlying questions can be used across product categories, but
the interpretation changes according to Product Vibe.

## 7.1 Problem Discovery

-   What are customers repeatedly complaining about?
-   Which workflows cause the most friction?
-   Which features are difficult to use?
-   What prevents customers from completing tasks?
-   What capabilities are customers requesting?

## 7.2 Product Reliability

-   Which features experience frequent failures?
-   Are customers reporting slow processing?
-   Are integrations creating problems?
-   Are users experiencing data loss or inconsistent results?
-   Which problems interrupt business-critical workflows?

## 7.3 Adoption and Retention

-   Which features are customers struggling to adopt?
-   What causes users to abandon workflows?
-   What makes customers consider switching platforms?
-   Which features generate positive feedback?
-   What capabilities could increase customer value?

## 7.4 Business Impact

-   Which problems affect the largest customer segments?
-   Which issues potentially increase support costs?
-   Which issues could threaten customer retention?
-   Which improvements could increase productivity?
-   Which problems should product teams investigate first?

### Analytical safeguards

-   Questions must be answered from available evidence.
-   Missing information must be marked as unknown.
-   Customer feedback is not proof of actual usage or revenue.
-   Retention risks are signals, not confirmed churn predictions.
-   Product recommendations must remain reviewable by humans.

------------------------------------------------------------------------

# 8. Core User Journey

1.  User opens ProductSignal.
2.  User creates a new product project.
3.  User enters product name and description.
4.  User selects Service-based → SaaS.
5.  User defines target customers and primary use case.
6.  ProductSignal activates SaaS Product Vibe.
7.  User uploads customer feedback.
8.  System validates and previews the dataset.
9.  AI classifies individual feedback records.
10. Similar feedback is grouped into problem clusters.
11. User explores clusters and supporting evidence.
12. ProductSignal ranks opportunities.
13. User selects an opportunity.
14. System generates an opportunity brief.
15. User reviews and approves the brief.
16. System generates an experiment hypothesis and draft PRD.
17. User edits and exports the final document.

------------------------------------------------------------------------

# 9. Product Dashboard Requirements

The MVP dashboard should contain the following sections:

### A. Overview

-   Total feedback records.
-   Successfully processed records.
-   Number of identified problem clusters.
-   High-priority opportunities.
-   Feedback source distribution.

### B. Problem Intelligence

-   Problem categories.
-   Recurring customer complaints.
-   Problem cluster details.
-   Representative feedback.
-   Customer segment distribution.

### C. Opportunity Prioritization

-   Ranked opportunities.
-   Opportunity scores.
-   Score breakdowns.
-   Supporting evidence.
-   Missing information indicators.

### D. Opportunity Workspace

-   Problem statement.
-   Evidence summary.
-   Customer impact.
-   Recommendations.
-   Experiment hypothesis.
-   PRD generation.

### E. Product Context

-   Product name.
-   Product category.
-   Target customers.
-   Primary use case.
-   Active Product Vibe.

------------------------------------------------------------------------

# 10. Data Strategy

## 10.1 Initial Data Sources

The MVP will use publicly available datasets, subject to their licensing
and attribution conditions.

Potential sources:

-   Customer Support Tickets Dataset from Kaggle.
-   Google Play Store Reviews Dataset from Kaggle.
-   Electronic Products Customer Review Dataset from Kaggle.

The initial implementation should prioritise support tickets and use app
reviews as an additional source if the available data is suitable.

## 10.2 Data Preparation

Before importing datasets:

1.  Inspect dataset structure.
2.  Record original source and license.
3.  Preserve original CSV files.
4.  Map relevant columns into the common feedback schema.
5.  Normalize date and text formats.
6.  Identify duplicate records.
7.  Handle missing values.
8.  Create a cleaned dataset.

Do not assume every dataset contains customer segments, product areas or
other metadata.

## 10.3 Evaluation Dataset

Create a manually labelled evaluation sample of approximately 100--150
records.

The sample should cover:

-   Reliability issues.
-   Performance issues.
-   Workflow problems.
-   Feature requests.
-   Onboarding issues.
-   Integration failures.
-   Positive feedback.
-   Ambiguous feedback.

This dataset will be used to evaluate classification and clustering
quality.

------------------------------------------------------------------------

# 11. Technical Architecture

## 11.1 Recommended Technology Stack

  -----------------------------------------------------------------------
  Layer                               Technology
  ----------------------------------- -----------------------------------
  Frontend                            Streamlit

  Application logic                   Python

  LLM                                 Local Ollama + Qwen initially

  Alternative inference               Free-tier providers, subject to
                                      current availability and limits

  Embeddings                          Sentence Transformers

  Vector search                       ChromaDB or FAISS

  Database                            SQLite

  Data processing                     Pandas

  Validation                          Pydantic

  Testing                             Pytest

  Version control                     GitHub
  -----------------------------------------------------------------------

The application must remain usable without paid API access.

## 11.2 Architecture Layers

### 1. Product Context Layer

-   Store product configuration.
-   Determine active Product Vibe.
-   Supply relevant context to downstream processing.

### 2. Ingestion Layer

-   Upload CSV.
-   Validate schema.
-   Normalize feedback.
-   Preserve original records.

### 3. AI Processing Layer

-   Classify feedback.
-   Generate summaries.
-   Extract problem categories.
-   Validate structured outputs.

### 4. Clustering Layer

-   Generate embeddings.
-   Calculate semantic similarity.
-   Group related feedback.
-   Identify representative records.

### 5. Prioritization Engine

-   Calculate frequency.
-   Evaluate severity.
-   Assess segment impact.
-   Calculate recency.
-   Evaluate business relevance.
-   Generate transparent rankings.

### 6. Product Intelligence Layer

-   Generate opportunity briefs.
-   Generate experiment hypotheses.
-   Draft PRDs.

### 7. Presentation Layer

-   Dashboard.
-   Feedback explorer.
-   Problem clusters.
-   Opportunity rankings.
-   Evidence explorer.
-   PRD editor.

## 11.3 Architecture Principle

Use AI for language understanding and synthesis.

Use deterministic Python logic for: - Calculations. - Validation. - Data
processing. - Scoring. - Database operations. - Evaluation metrics.

This separation is essential for reliability and explainability.

------------------------------------------------------------------------

# 12. Database Requirements

The initial database should contain the following logical entities:

  Entity                 Purpose
  ---------------------- -----------------------------------------
  products               Product configuration and context
  feedback               Original customer feedback
  classifications        AI-generated feedback classifications
  clusters               Identified customer problem groups
  cluster_feedback       Mapping between clusters and feedback
  opportunities          Prioritized product opportunities
  opportunity_evidence   Evidence supporting opportunities
  briefs                 Generated opportunity briefs
  experiments            Generated experiment hypotheses
  prds                   Generated product requirement documents

Every analysis record should be associated with its product project.

This will make future multi-product support easier without requiring a
complete database redesign.

------------------------------------------------------------------------

# 13. Non-Functional Requirements

## Performance

-   Support a demonstration dataset of approximately 500 feedback
    records.
-   Show processing status.
-   Support batch processing.
-   Avoid blocking the interface during longer operations.

## Reliability

-   Validate structured model responses.
-   Handle timeouts and malformed outputs.
-   Preserve original feedback if AI processing fails.
-   Allow failed records to be retried.

## Explainability

-   Display original customer feedback.
-   Link clusters to supporting records.
-   Explain opportunity scoring.
-   Distinguish facts from AI-generated assumptions.

## Privacy

-   Use synthetic or appropriately licensed public data for the
    portfolio demonstration.
-   Avoid uploading confidential customer information to external
    models.
-   Keep the MVP local by default.

## Maintainability

-   Keep product configuration separate from core analysis logic.
-   Use modular Python components.
-   Keep prompts version-controlled.
-   Store scoring weights as configuration rather than hardcoding them
    throughout the application.

------------------------------------------------------------------------

# 14. Key Product Metrics

## 14.1 North Star Metric

**Evidence-backed opportunities reviewed and accepted by product
teams.**

The purpose of ProductSignal is not simply to process more comments. It
is to help product teams make better decisions.

## 14.2 Operational Metrics

  -----------------------------------------------------------------------
  Metric                              Purpose
  ----------------------------------- -----------------------------------
  Feedback processing success rate    Measure processing reliability

  Classification accuracy             Measure category assignment quality

  Classification correction rate      Measure manual correction required

  Cluster precision                   Measure quality of problem grouping

  Cluster coverage                    Measure feedback represented in
                                      clusters

  Evidence traceability               Measure whether claims link to
                                      source records

  Opportunity review time             Measure decision workflow
                                      efficiency

  PRD editing effort                  Measure usefulness of generated
                                      drafts
  -----------------------------------------------------------------------

## 14.3 Proposed MVP Evaluation Targets

These are test targets, not achieved results.

-   At least 90% of imported records successfully processed.
-   At least 80% precision on a manually reviewed sample of problem
    clusters.
-   At least 90% of factual opportunity claims traceable to source
    feedback.
-   All opportunity scores reproducible from underlying scoring inputs.
-   No unsupported customer claims presented as verified facts.

Evaluation should use manually labelled records and human review, not
LLM self-assessment alone.

------------------------------------------------------------------------

# 15. Risks and Mitigation

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  Incorrect feedback classification   Manual review and confidence flags

  Poor problem clustering             Similarity tuning and manual
                                      correction

  Hallucinated insights               Evidence references and
                                      source-grounded generation

  Biased prioritization               Transparent configurable scoring

  Missing customer metadata           Explicit unknown values

  Slow local inference                Batch processing and model
                                      optimisation

  Dataset bias                        Document dataset limitations

  Overcomplicated MVP                 Strict P0 scope
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 16. MVP Scope and Priorities

  Feature                              Priority
  ------------------------------------ ----------
  Product Context Setup                P0
  SaaS Product Vibe                    P0
  CSV ingestion                        P0
  Data validation and preview          P0
  AI feedback classification           P0
  Problem clustering                   P0
  Evidence explorer                    P0
  Opportunity scoring                  P0
  Opportunity brief generation         P0
  Experiment hypothesis generation     P1
  Editable PRD generation              P1
  Report export                        P1
  Manual cluster correction            P1
  Custom scoring weights               P2
  Consumer Product Vibe                P2
  Multi-product portfolio management   P2
  Cross-product benchmarking           P2

P0 features are essential for the core MVP. P1 features should be
attempted after the core workflow is working. P2 features are outside
the initial build.

------------------------------------------------------------------------

# 17. Seven-Day Development Roadmap

## Day 1 --- Product Foundation

-   Finalise product flows.
-   Create synthetic SaaS product context.
-   Inspect and select Kaggle datasets.
-   Define feedback schema.
-   Create database schema.
-   Design basic dashboard wireframes.

**Deliverable:** Product foundation and data specification.

## Day 2 --- Ingestion

-   Build CSV uploader.
-   Implement column mapping.
-   Validate datasets.
-   Preview records.
-   Store feedback in SQLite.

**Deliverable:** Working ingestion module.

## Day 3 --- AI Classification

-   Configure local LLM.
-   Create SaaS classification taxonomy.
-   Implement structured prompts.
-   Validate outputs with Pydantic.
-   Store classifications.

**Deliverable:** Working feedback classification.

## Day 4 --- Problem Clustering

-   Generate embeddings.
-   Implement similarity-based grouping.
-   Identify representative feedback.
-   Display problem clusters.

**Deliverable:** Working problem discovery module.

## Day 5 --- Prioritization

-   Implement deterministic scoring.
-   Display opportunity rankings.
-   Add scoring breakdowns.
-   Link opportunities to original evidence.

**Deliverable:** Opportunity intelligence dashboard.

## Day 6 --- Product Outputs

-   Generate opportunity briefs.
-   Generate experiment hypotheses.
-   Implement draft PRD generation if time permits.
-   Add editing and export capabilities where feasible.

**Deliverable:** Product decision workflow.

## Day 7 --- Testing and Portfolio

-   Test the complete workflow.
-   Evaluate classification and clustering.
-   Inspect unsupported claims.
-   Fix critical failures.
-   Record product demonstration.
-   Prepare GitHub README and product case study.

**Deliverable:** Demonstrable local MVP and portfolio documentation.

------------------------------------------------------------------------

# 18. Future Product Roadmap

## Phase 2 --- Multi-Product Intelligence

Allow users to create and manage multiple product projects.

Each project can have its own: - Product context. - Product type. -
Product category. - Target customers. - Product Vibe. - Analytical
configuration. - Feedback datasets. - Opportunity history.

Introduce the Consumer Product Vibe with categories such as: - Mobile
applications. - E-commerce. - Food delivery. - Streaming. - Consumer
products.

## Phase 3 --- Advanced Product Intelligence

-   Emerging problem detection.
-   Historical feedback trends.
-   Customer segment comparisons.
-   Product release impact analysis.
-   Advanced opportunity scoring.
-   Custom analytical questions.
-   Custom scoring frameworks.

## Phase 4 --- Integrations

-   Google Play reviews.
-   App Store reviews.
-   Zendesk.
-   Intercom.
-   Jira.
-   Linear.
-   Other supported feedback platforms.

## Phase 5 --- Product Portfolio Intelligence

-   Cross-product opportunity comparison.
-   Product-level performance summaries.
-   Shared problem detection.
-   Portfolio-level prioritization.
-   Executive product intelligence reports.

These capabilities are future roadmap items, not MVP commitments.

------------------------------------------------------------------------

# 19. Product Differentiation

ProductSignal should not position itself as another sentiment-analysis
dashboard or generic AI chatbot.

Its differentiation is the combination of:

1.  Product-specific context.
2.  Context-aware Product Vibe.
3.  Structured customer problem discovery.
4.  Evidence-backed opportunity prioritization.
5.  Product action generation.

The complete product workflow:

**Product Context → Product Vibe → Customer Feedback → Problem Clusters
→ Evidence → Prioritization → Opportunity Brief → Experiment → PRD**

The shared intelligence engine should support different product
perspectives without rebuilding the core system for every product
category.

------------------------------------------------------------------------

# 20. MVP Definition of Done

The MVP will be considered complete when:

1.  A user can create a SaaS product project.
2.  Product Context Setup stores the product's details.
3.  SaaS Product Vibe is activated.
4.  A user can upload a valid customer feedback dataset.
5.  The application validates and imports feedback.
6.  The LLM classifies feedback into structured categories.
7.  Similar feedback is grouped into problem clusters.
8.  Users can inspect supporting customer evidence.
9.  Opportunities are ranked using deterministic scoring.
10. Users can inspect opportunity score components.
11. Users can generate an evidence-backed opportunity brief.
12. The complete workflow can be demonstrated locally.
13. Evaluation results and limitations are documented.

Experiment and PRD generation are important enhancements, but they must
not delay a reliable end-to-end core workflow.

------------------------------------------------------------------------

# 21. Portfolio Deliverables

The completed project should include:

1.  Working local MVP.
2.  Final PRD V2.
3.  System architecture diagram.
4.  Database schema.
5.  Public dataset source and attribution documentation.
6.  Cleaned and normalized feedback dataset.
7.  Manually labelled evaluation dataset.
8.  Product prioritization framework.
9.  AI classification and clustering evaluation results.
10. Functional demonstration video.
11. GitHub repository with setup instructions.
12. Product case study explaining decisions, trade-offs, limitations and
    measured results.

### Portfolio Positioning

**AI Product Management \| Product Discovery \| Customer Intelligence \|
AI Workflow Design \| Product Strategy \| Product Analytics**

Do not claim business impact, model accuracy or time savings until those
outcomes have been measured.

------------------------------------------------------------------------

# Final Product Principle

**ProductSignal is not designed to tell product teams what customers
feel. It is designed to help product teams understand what customers
need, identify which problems matter most, and decide what to do
next---with evidence.**
