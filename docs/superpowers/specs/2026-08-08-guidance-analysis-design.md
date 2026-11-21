# Guidance & Product-Line Credibility Tracker — Design

**Date:** 2026-08-08
**Status:** Approved for planning
**Extends:** `chain_survey` (Fundamental Chain Reaction Platform)

## Purpose

Extend chain_survey so it can answer two recurring questions for the 14 tracked
companies:

1. **Guidance credibility** — when management makes forward-looking statements
   in an earnings call (法說會), how often does the actual subsequent quarterly
   report bear them out?
2. **Product-line signal** — which product lines / business segments a company
   talks about are actually supported by the company's overall financial
   trend, versus talked-up but never corroborated?

The system treats every forward-looking statement from an earnings call as a
trackable **claim**, which moves through extraction, human review, and
verification against official financial data already in chain_survey's data
model.

## Scope

- Companies: the existing 14 in `data/company_master.csv`. No new-company
  onboarding flow in this phase.
- Source material: PDF earnings call decks / transcripts you already have on
  hand. No scraping/ingestion automation from MOPS or IR sites in this phase.
- Verification is against data already in `quarterly_financials.csv` and
  `monthly_revenue.csv` — no new external financial data source.

## Data Model

Three new CSV tables under `chain_survey/data/`, following the existing
ticker-keyed convention:

### `source_documents.csv`
Registry of ingested earnings call files.

| field | description |
|---|---|
| `doc_id` | unique id |
| `ticker` | company ticker, FK to `company_master.csv` |
| `file_path` | path to the PDF under `data/raw_transcripts/<ticker>/` |
| `source_quarter` | the quarter the earnings call was held for, e.g. `114Q2` |
| `call_date` | date of the earnings call |

### `guidance_claims.csv`
Structured claims extracted from a source document.

| field | description |
|---|---|
| `claim_id` | unique id |
| `doc_id` | FK to `source_documents.csv` |
| `ticker` | company ticker |
| `source_quarter` | quarter the claim was made in |
| `target_period` | future quarter the claim is about, e.g. `114Q3` |
| `category` | `revenue_growth` \| `gross_margin` \| `product_line` \| `capex` \| `other` |
| `product_or_segment` | free-text product/segment label, nullable |
| `direction` | `up` \| `down` \| `flat` |
| `quant_low`, `quant_high` | quantitative range if management gave one, nullable |
| `raw_text` | verbatim excerpt the claim was extracted from |
| `status` | `pending_review` \| `confirmed` \| `rejected` |
| `reviewed_by`, `reviewed_at` | set on review |

### `claim_outcomes.csv`
Verification results, populated once `target_period` actuals are available.

| field | description |
|---|---|
| `claim_id` | FK to `guidance_claims.csv` |
| `actual_value` | computed actual (QoQ/YoY change, matching the claim's field) |
| `match_result` | `match` \| `partial` \| `miss` \| `unverifiable` |
| `evaluated_at` | when the verification ran |
| `note` | free-text, e.g. why marked `unverifiable` |

## Pipeline

### 1. Ingestion
PDFs are placed under `data/raw_transcripts/<ticker>/<quarter>.pdf`. A script
scans this directory, derives `ticker`/`source_quarter` from the path, and
registers new files into `source_documents.csv`. `call_date` is filled from
filename convention or entered manually.

### 2. LLM Extraction
For each new `source_documents.csv` row, extract PDF text and send it to the
Claude API with a fixed prompt that returns a JSON list of claims matching the
`guidance_claims.csv` schema. Extraction rules:

- Only forward-looking statements (guidance, product-line outlook) are
  extracted — not restatements of already-published historical numbers.
- Every extracted claim must carry `raw_text`, the exact excerpt it was drawn
  from, so a reviewer can verify against source rather than trust an LLM
  summary.
- All extracted claims start as `status = pending_review`.

### 3. Human Review (GUI)
A new top-level "Guidance Review" tab in `gui_app.py` lists all
`pending_review` claims. For each: show `raw_text` alongside the extracted
fields, with confirm / edit / reject actions. Confirming sets
`status = confirmed` and stamps `reviewed_by`/`reviewed_at`; only confirmed
claims feed into verification and scoring. This gate exists because this is a
fact-checking tool — unreviewed extraction errors quietly corrupting the
credibility score would defeat its purpose.

### 4. Verification Engine (rule-based, no LLM)
Runs whenever `quarterly_financials.csv` / `monthly_revenue.csv` are
refreshed. For every `confirmed` claim whose `target_period` now has actual
data:

- Compute the relevant actual change (QoQ/YoY, matching `category`'s field —
  e.g. `revenue_growth` claims compare against `revenue`, `gross_margin`
  claims against `gross_margin`).
- If `quant_low`/`quant_high` present: actual within range → `match`;
  right direction but outside range → `partial`; wrong direction → `miss`.
- If no quantitative range (direction-only claim): compare sign only →
  `match` or `miss`.
- Write the result to `claim_outcomes.csv`.

Company-level **guidance credibility score** = match ratio over the trailing
N quarters of resolved claims (e.g. match=1, partial=0.5, miss=0 point,
averaged).

## Product-Line Signal: Proxy Methodology (data limitation)

Taiwan's official disclosures (TWSE/MOPS monthly revenue, quarterly filings)
are company-level only — there is no official quarterly product-line revenue
breakdown for most companies. Direct per-product-line reconciliation is not
possible with the data this system has access to.

Instead, product-line claims (`category = product_line`) are evaluated with a
**directional cross-verification proxy**, not a financial reconciliation:

1. **Consistency across quarters** — does the same `product_or_segment` keep
   being mentioned with a consistent direction across consecutive earnings
   calls, or does it appear once and disappear?
2. **Correlation with company-level trend** — when a product line is claimed
   to be driving growth/margin, does the company's overall `revenue` /
   `gross_margin` in the corresponding `target_period` actually move in that
   direction? A match raises confidence in the claim; a mismatch lowers it.
3. Annual report segment disclosures, where a company happens to publish
   them, may be layered in later as a once-a-year supplementary signal — not
   required for this phase.

This proxy answers "is management's story about this product line being
corroborated by the company's overall numbers, consistently, over time?" —
not "how much revenue did this product line make." That distinction should be
visible in the GUI (see below), not just documented here.

## GUI Integration

Built on the existing `ttk.Notebook` structure in `chain_survey/app/gui_app.py`.

1. **New top-level tab: "Guidance Review"** — the human-review queue described
   in Pipeline step 3.
2. **New sub-tab "Guidance Tracker" inside Company Explorer's existing
   `relation_notebook`** (alongside Upstream/Downstream/Products):
   - Top: trailing-quarters guidance credibility score trend (match/partial/
     miss ratio) for the selected company.
   - Bottom: per-product-line claim timeline, color-coded — green
     (direction corroborated by financials), yellow (partial/mixed), grey
     (target period not yet resolved).

## Testing

- Verification/scoring logic (claim vs. actuals → match/partial/miss, score
  aggregation) gets pytest unit tests under `chain_survey/tests/`, following
  existing test conventions, using synthetic claims + financials fixtures.
- LLM extraction is not covered by automated correctness assertions (LLM
  output isn't deterministic); validated manually against 1–2 real PDFs to
  confirm schema/field usability before wider use.
- New GUI tabs are validated manually by running the app, consistent with how
  the rest of `gui_app.py` is currently verified.

## Out of Scope (this phase)

- Onboarding companies beyond the existing 14.
- Automated scraping/ingestion of earnings call material from MOPS or IR
  sites.
- Per-product-line financial reconciliation (blocked by data availability,
  see Proxy Methodology above).
- News/rumor verification against financials (separate future track; this
  phase covers management guidance only).
