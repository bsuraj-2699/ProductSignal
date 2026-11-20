# ProductSignal
## AI-Powered Customer Feedback Intelligence & Product Discovery Platform

**Document type:** Product Requirements Document (PRD)  
**Version:** 1.0  
**Status:** MVP — Proposed  
**Target build:** 7 days  
**Primary users:** Product Managers, Product Analysts, Product Operations teams

---

## 1. Product Overview

### 1.1 Problem Statement

Product teams receive customer feedback from multiple disconnected sources, including app reviews, support tickets, surveys, interviews, and feature requests.

However, this feedback is often:
- Scattered across different platforms and formats.
- Repetitive, with the same underlying issue described differently.
- Difficult to prioritize objectively.
- Disconnected from product roadmap decisions.
- Time-consuming to convert into actionable product requirements.

As a result, product teams risk prioritizing loud opinions instead of high-impact customer problems.

### 1.2 Proposed Solution

ProductSignal is an AI-powered customer feedback intelligence platform that transforms unstructured feedback into structured product insights.

It helps product teams:
1. Import customer feedback from multiple sources.
2. Identify recurring problems and emerging themes.
3. Group feedback by customer segment and product area.
4. Prioritize opportunities using configurable scoring.
5. Generate evidence-backed opportunity briefs.
6. Convert selected opportunities into experiment hypotheses and draft PRDs.

**Core value proposition:** Move from thousands of customer comments to a prioritized, evidence-backed product roadmap.

### 1.3 Product Vision

Become a decision-support layer between customer feedback and product strategy, helping teams understand not just what customers are saying, but what the product team should investigate next and why.

---

## 2. Target Users

### Primary Persona: Product Manager

**Responsibilities:**
- Understand customer problems.
- Prioritize product improvements.
- Coordinate with engineering and design teams.
- Maintain product roadmaps.

**Pain points:**
- Too much feedback and too little time.
- Difficulty identifying recurring problems.
- Lack of evidence behind feature requests.
- Stakeholder pressure to prioritize individual requests.

**Desired outcome:** Make faster, defensible prioritization decisions.

### Secondary Persona: Product Operations Analyst

**Responsibilities:**
- Collect feedback from multiple channels.
- Maintain customer insight repositories.
- Identify recurring issues.
- Prepare product performance reports.

**Pain points:**
- Manual categorization.
- Repetitive reporting.
- Inconsistent feedback classification.

**Desired outcome:** Automate feedback analysis and produce reliable insight reports.

---

## 3. Goals and Non-Goals

### Product Goals

1. Reduce the manual effort required to categorize feedback.
2. Identify recurring customer problems across feedback sources.
3. Provide transparent, evidence-backed opportunity prioritization.
4. Help PMs convert customer problems into actionable product documents.
5. Keep humans in control of roadmap decisions.

### Non-Goals for MVP

- Replacing Jira, Linear, Productboard, or other roadmap tools.
- Automatically making roadmap decisions.
- Real-time integrations with every customer feedback platform.
- Predicting revenue impact without supporting data.
- Building a general-purpose chatbot.
- Fully autonomous PRD generation without human review.

---

## 4. MVP Scope

### Feature 1: Feedback Ingestion

**Description:** Allow users to upload customer feedback in CSV format.

Supported fields:
- Feedback ID
- Feedback text
- Source
- Date
- Customer segment
- Product area
- Rating (optional)

**Requirements:**
- CSV upload.
- Column mapping and validation.
- Duplicate detection.
- Missing-field handling.
- Preview before importing.
- Sample dataset for demonstration.

**Acceptance criteria:**
- Users can upload a valid CSV.
- Invalid rows are identified with clear error messages.
- Users can preview records before importing.
- Imported records are stored in the database.

### Feature 2: AI Feedback Classification

**Description:** Use an LLM to classify individual feedback records.

Each record should receive:
- Primary problem category.
- Product area.
- Sentiment or emotional tone.
- Problem severity.
- Customer intent.
- Short summary.

Example:

Customer feedback:
"The application keeps crashing whenever I try to upload a large PDF."

Classification:
- Category: Reliability
- Product area: File Upload
- Sentiment: Negative
- Severity: High
- Customer intent: Report a technical issue
- Summary: Application crashes during large PDF uploads.

**Requirements:**
- Structured JSON output.
- Pydantic validation.
- Retry handling for malformed responses.
- Store model output and original feedback separately.
- Mark uncertain classifications for review.

**Acceptance criteria:**
- Feedback is classified into a consistent schema.
- Invalid model outputs do not silently enter the database.
- Users can inspect the original feedback alongside its classification.
- Low-confidence outputs are flagged rather than presented as facts.

### Feature 3: Problem Clustering

**Description:** Identify recurring customer problems across feedback records.

The system should group similar feedback into problem clusters.

Example:

| Feedback | Identified problem |
|---|---|
| "Upload keeps failing" | File upload reliability |
| "PDF upload gets stuck" | File upload reliability |
| "Large documents won't upload" | File upload reliability |

Each cluster should contain:
- Problem title.
- Problem description.
- Number of related feedback records.
- Representative customer comments.
- Feedback source distribution.
- Affected customer segments.
- First and most recent observed dates.

**Requirements:**
- Semantic similarity-based grouping.
- Configurable clustering threshold.
- Representative examples.
- Ability to inspect and manually correct cluster assignments.

**Acceptance criteria:**
- Similar feedback can be grouped together.
- Users can inspect the evidence behind every cluster.
- Users can separate incorrectly grouped feedback.
- The system does not invent customer comments or evidence.

### Feature 4: Opportunity Prioritization

**Description:** Rank problem clusters using a transparent prioritization framework.

MVP scoring dimensions:

| Dimension | Weight |
|---|---:|
| Frequency | 30% |
| Severity | 25% |
| Customer segment impact | 20% |
| Recency | 15% |
| Business relevance | 10% |

Each dimension receives a score from 1 to 5.

**Opportunity Score:**

Weighted score = Sum of (dimension score × dimension weight)

The final score is normalized to 100.

Example:

| Dimension | Score | Weight |
|---|---:|---:|
| Frequency | 5 | 30% |
| Severity | 4 | 25% |
| Segment impact | 4 | 20% |
| Recency | 5 | 15% |
| Business relevance | 3 | 10% |

The system must show:
- Overall opportunity score.
- Individual dimension scores.
- Reasoning behind each score.
- Supporting feedback records.
- Missing information or assumptions.

**Important product decision:** The LLM may recommend scores and explain them, but deterministic application logic calculates the final score. Users can adjust weights and review recommendations.

### Feature 5: Opportunity Brief Generator

**Description:** Convert a selected problem cluster into a structured opportunity brief.

The brief should include:

1. Problem statement.
2. Customer impact.
3. Evidence summary.
4. Affected segments.
5. Frequency and severity.
6. Current limitations.
7. Potential product opportunities.
8. Risks and assumptions.
9. Recommended next steps.

Every factual claim should link back to supporting feedback records.

### Feature 6: Experiment Hypothesis Generator

**Description:** Generate testable product hypotheses from an approved opportunity.

Example:

**Problem:** Customers experience frequent failures when uploading large documents.

**Hypothesis:** If we introduce resumable uploads and clearer upload progress indicators, users will experience fewer failed uploads and complete more document submissions.

**Suggested experiment:**
- Target segment: Users uploading large documents.
- Success metric: Upload completion rate.
- Secondary metric: Upload-related support tickets.
- Test approach: A/B test or controlled rollout.
- Guardrail: Upload processing time.

The system should distinguish between suggested metrics and measured results.

### Feature 7: Draft PRD Generator

**Description:** Convert an approved opportunity into a first-draft PRD.

Generated sections:
- Problem statement.
- User personas.
- Goals and non-goals.
- User stories.
- Functional requirements.
- Acceptance criteria.
- Success metrics.
- Risks and dependencies.
- Open questions.

The PRD must be editable before export.

---

## 5. Core User Journey

1. User opens ProductSignal.
2. User uploads a CSV containing customer feedback.
3. System validates and imports the records.
4. AI classifies individual feedback.
5. Similar feedback is grouped into problem clusters.
6. User explores clusters and supporting evidence.
7. System ranks opportunities using the prioritization framework.
8. User selects an opportunity.
9. ProductSignal generates an opportunity brief.
10. User reviews the evidence and approves the opportunity.
11. System generates an experiment hypothesis and draft PRD.
12. User edits and exports the final document.

---

## 6. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Upload CSV feedback | P0 |
| FR-02 | Validate and preview data | P0 |
| FR-03 | Classify feedback using an LLM | P0 |
| FR-04 | Group similar feedback | P0 |
| FR-05 | Display evidence-backed clusters | P0 |
| FR-06 | Calculate opportunity scores | P0 |
| FR-07 | Generate opportunity briefs | P0 |
| FR-08 | Generate experiment hypotheses | P1 |
| FR-09 | Generate editable PRDs | P1 |
| FR-10 | Export reports | P1 |
| FR-11 | Allow manual correction of clusters | P1 |
| FR-12 | Configure prioritization weights | P2 |

**P0:** Required for a usable MVP.  
**P1:** Important enhancement if time permits.  
**P2:** Future enhancement.

---

## 7. Non-Functional Requirements

### Performance
- Process a demonstration dataset of approximately 500 feedback records.
- Show processing status to users.
- Avoid blocking the interface during longer model operations.

### Reliability
- Validate structured model responses.
- Handle timeouts and malformed responses.
- Preserve original feedback even if AI processing fails.
- Allow failed records to be retried.

### Explainability
- Show supporting feedback for each identified problem.
- Display how opportunity scores are calculated.
- Clearly label assumptions and AI-generated recommendations.

### Privacy
- Use synthetic data for the portfolio demonstration.
- Do not send private customer information to external model providers.
- Keep the MVP local by default.

---

## 8. AI and Technical Architecture

### Recommended Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | Python |
| LLM | Ollama + locally hosted Qwen |
| Embeddings | Sentence Transformers |
| Vector Search | ChromaDB or FAISS |
| Database | SQLite |
| Data Processing | Pandas |
| Validation | Pydantic |
| Testing | Pytest |
| Version Control | GitHub |

### Architecture

**1. Ingestion Layer**
- Accept CSV files.
- Validate schemas.
- Normalize records.
- Store original feedback.

**2. AI Processing Layer**
- Classify feedback.
- Generate structured summaries.
- Extract customer problems.
- Validate model outputs.

**3. Clustering Layer**
- Generate embeddings.
- Calculate semantic similarity.
- Group similar feedback.
- Identify representative records.

**4. Prioritization Engine**
- Calculate frequency.
- Estimate severity and segment impact.
- Apply weighted scoring.
- Generate transparent ranking explanations.

**5. Product Intelligence Layer**
- Generate opportunity briefs.
- Generate experiment hypotheses.
- Draft PRDs.

**6. Presentation Layer**
- Feedback overview.
- Problem clusters.
- Opportunity ranking.
- Evidence explorer.
- PRD editor/export.

### Architecture Principle

Use AI for language understanding and synthesis. Use deterministic Python logic for calculations, validation, scoring, and data handling.

This separation is essential for reliability.

---

## 9. Key Product Metrics

### North Star Metric

**Evidence-backed opportunities reviewed and accepted by product teams.**

This is more meaningful than the number of feedback records processed.

### Operational Metrics

| Metric | Purpose |
|---|---|
| Feedback processing time | Measure workflow efficiency |
| Classification correction rate | Measure AI classification quality |
| Cluster precision | Measure grouping quality |
| Cluster coverage | Measure how much feedback is grouped |
| Opportunity review time | Measure decision efficiency |
| Evidence traceability | Measure whether claims link to source feedback |
| PRD editing effort | Measure usefulness of generated drafts |

### MVP Evaluation Targets

These are proposed test targets, not achieved results:

- At least 90% of imported records successfully processed.
- At least 80% precision on a manually reviewed sample of problem clusters.
- At least 90% of opportunity claims traceable to source feedback.
- All prioritization scores reproducible from the underlying scoring inputs.

Evaluate quality on a manually labeled test set rather than relying on LLM self-assessment.

---

## 10. Risks and Mitigation

| Risk | Mitigation |
|---|---|
| Incorrect feedback classification | Manual review and confidence flags |
| Poor clustering | Similarity threshold tuning and manual correction |
| Hallucinated insights | Evidence references and source-grounded generation |
| Biased prioritization | Transparent configurable scoring |
| Slow local LLM inference | Batch processing and smaller models |
| Overcomplicated MVP | Strict P0 feature scope |

---

## 11. MVP Success Criteria

The MVP will be considered complete when:

1. A user can upload a feedback dataset.
2. The system classifies feedback into structured categories.
3. Related feedback is grouped into problem clusters.
4. Each cluster displays representative customer evidence.
5. Opportunities are ranked using a transparent scoring framework.
6. A user can generate an opportunity brief.
7. A user can generate and edit a draft PRD.
8. The workflow can be demonstrated end-to-end without paid APIs.

---

## 12. Future Roadmap

### Phase 2 — Integrations
- Google Play reviews.
- App Store reviews.
- Zendesk.
- Intercom.
- Jira.
- Linear.

### Phase 3 — Advanced Intelligence
- Emerging problem detection.
- Customer segment comparisons.
- Feedback trend analysis.
- Product release impact analysis.
- Historical opportunity tracking.

### Phase 4 — Collaboration
- Team workspaces.
- Opportunity approval workflows.
- Roadmap integrations.
- Stakeholder comments.
- Product decision history.

---

## 13. Product Differentiation

ProductSignal should not compete by claiming to be another AI sentiment-analysis platform.

Its differentiation is the complete workflow:

**Raw Feedback → Customer Problems → Evidence → Prioritization → Opportunity Brief → Experiment → PRD**

The product should make it easy to answer three questions:

1. What problems are customers repeatedly experiencing?
2. Which problems deserve product attention first, and what evidence supports that decision?
3. What should the product team do next?

That decision-making workflow is the product.

---

## 14. Portfolio Demonstration Deliverables

The completed project should include:

1. Working local MVP.
2. Product requirements document.
3. System architecture diagram.
4. Synthetic customer feedback dataset.
5. Manually labeled evaluation dataset.
6. Product prioritization framework.
7. Functional demonstration video.
8. GitHub repository with setup instructions.
9. Product case study covering decisions, trade-offs, limitations, and evaluation results.

**Portfolio positioning:** AI Product Management | Customer Intelligence | Product Discovery | AI Workflow Design | Product Prioritization

**Important:** Do not claim business impact, accuracy, or time savings until they have been measured through actual tests.
