# Fundamental Alpha Research Platform

chain_survey is the main research product in a three-repository investment research stack.

The platform is built around one idea:

> Do not start from price prediction. Start from where industry profit is moving, identify the operating driver, connect it to products and companies, validate the relation point-in-time, and only then translate it into earnings and investment hypotheses.

Core causal chain:

~~~
Industry / demand evidence
        ↓
Demand / supply state
        ↓
Industry driver
        ↓
Product economics
        ↓
Company exposure
        ↓
Revenue / margin / EPS
        ↓
Turnaround / inflection
        ↓
Expectation gap
        ↓
Valuation / strategy validation
~~~

## Repository roles

| Repository | Responsibility | What it should NOT become |
| --- | --- | --- |
| chain_survey | Fundamental research, evidence, causal drivers, product economics, company impact, turnaround, research runs | A generic trading/backtest framework |
| invest_backtest | Strategy validation, walk-forward, costs, portfolio/risk, performance | A second copy of fundamental research logic |
| market-temperature-dashboard | Macro / market-regime context and risk state | A company-level stock picker |

Target contract flow:

~~~
market-temperature-dashboard
        │
        │ MarketRegimeV1
        ▼
chain_survey
        │
        │ ResearchSignalV1 / ValidatedDriver
        ▼
invest_backtest
        │
        │ BacktestResultV1
        ▼
research feedback
~~~

chain_survey remains the main research workspace.

---

## What is implemented today

### 1. Real point-in-time evidence

Evidence rows keep both the economic period and the time the data became knowable.

Important fields include:

~~~
period_date
published_at
raw_value
source
source_type
reliability
transform
transform_version
provenance
~~~

Historical scoring enforces:

~~~
published_at <= evaluation_as_of_date
~~~

so unpublished data cannot leak into historical research.

Current free evidence families include:

- TWSE / MOPS-derived company monthly revenue
- Taiwan MOEA export orders
- TSMC monthly revenue
- TPCA PCB / material / CCL public industry data
- TrendForce public DRAM price snapshots

TrendForce public history is append-only because the complete historical download is not freely exposed. The system does not fabricate missing history.

### 2. Evidence-based demand inference

The demand engine does not accept a headline such as "AI demand is strong" as a fact.

Each observation is normalized and discounted:

~~~
Effective Evidence
=
Normalized Signal
× Source Reliability
× Freshness
~~~

Repeated reports describing the same causal event are collapsed by evidence_group before aggregation.

The engine separates:

- Buyer Commitment
- Orders / Backlog
- Physical Throughput
- Market Tightness
- Financial Confirmation

Independent supply-chain confirmations increase confidence; duplicate narratives do not.

Run:

~~~
python app/main.py --demand-evidence
~~~

### 3. Industry Driver Models

Industry logic is config-driven rather than hard-coded into the UI.

Current models:

- IC Substrate — ABF / BT
- Memory — DRAM / HBM / NAND
- Foundry — Advanced Node
- CCL / PCB — High Speed

Each model can define:

~~~
Demand equation
Supply equation
Revenue equation
Margin equation
Drivers
Evidence mappings
Financial bridge
~~~

Example ABF model:

~~~
ABF demand
=
Chip shipment
× Substrate area per chip
× Layer / complexity factor

Revenue
=
Shipment volume × ASP

Gross margin
=
f(ASP, utilization, mix, yield, material cost)
~~~

Run:

~~~
python app/main.py --industry-driver
~~~

### 4. Historical free-evidence panel

The free evidence history is persisted separately and rebuilt into a correlation-ready panel.

Current persisted history includes:

- ABF company monthly revenue history for 欣興 / 景碩 / 南電
- TPCA PCB / material / CCL monthly history
- append-only TrendForce public DRAM snapshots

The history pipeline checks:

- no duplicate source + metric + period keys
- publication time is never earlier than the economic period
- minimum coverage for correlation eligibility
- parser behavior through fixtures/tests

TrendForce metrics are excluded from correlation ranking until enough observations exist.

### 5. Point-in-time operating correlation

Candidate industry indicators are tested against future operating fundamentals, not immediately against stock returns.

The first operating scan currently tests TPCA industry metrics against:

- 欣興 monthly revenue YoY
- 景碩 monthly revenue YoY
- 南電 monthly revenue YoY
- median ABF revenue basket

For each feature / target / lag combination, the engine calculates:

- Spearman correlation
- Pearson correlation
- sample size
- first-half / second-half stability
- chronological 70/30 OOS correlation
- lag from 0–6 months

Positive lag means the industry feature leads the target.

### 6. Validated Driver Pipeline

High correlation alone is not enough to enter the industry model.

Candidate drivers pass through:

~~~
Point-in-time validity
        ↓
Sample-size gate
        ↓
Rolling 12M / 18M stability
        ↓
Cross-company generalization
        ↓
Chronological OOS
        ↓
Moving-block bootstrap
        ↓
Block permutation test
        ↓
Nested walk-forward lag selection
        ↓
Benjamini-Hochberg FDR
        ↓
VALIDATED
~~~

Current status ladder:

~~~
EXPERIMENTAL
    ↓
CANDIDATE
    ↓
VALIDATED
    ↓
PRODUCTION
    ↓
RETIRED
~~~

A driver cannot be promoted simply because it has the largest correlation.

### 7. First validated empirical relation

The first relation that passed the full validation pipeline is:

~~~
TPCA PCB Revenue YoY
        ↓
lead 1 month
        ↓
ABF Revenue YoY Basket
~~~

Validation snapshot:

~~~
Samples                    31
Spearman                 +0.580
Pearson                  +0.634
Chronological OOS        +0.515
Rolling sign share        85.3%
Cross-company sign share 100.0%
Walk-forward OOS median  +0.800
Permutation p             0.007
FDR q                     0.042
Robustness gates           6 / 6
~~~

This relation is stored in:

~~~
data/validated_driver_registry.json
~~~

and attached to the ABF end_demand driver as an EMPIRICALLY_LINKED relation.

Important design choice:

> Validation does not add the same signal a second time.

The TPCA observation already contributes through the evidence engine. The validated relation upgrades its evidence status, lag knowledge, and confidence/explanation layer instead of double-counting the signal.

### 8. ResearchRunV1

Every robust validation run records its research context.

A research run contains:

~~~
research_run_id
question
created_at
code_sha
evidence_snapshot_sha
history_path
methodology
candidate_count
validated_count
results
~~~

This makes a research conclusion reproducible against the exact code and data snapshot used at the time.

### 9. Product / company earnings bridge

The product earnings layer models:

~~~
Product revenue = Volume × ASP

Product gross profit = Revenue × Gross margin
~~~

and bridges product-level changes into:

~~~
Operating income
→ Pre-tax income
→ Net income
→ EPS
~~~

The platform also supports multi-product EPS attribution.

### 10. Turnaround / inflection radar

The turnaround engine looks for improving operating fundamentals rather than merely low prices.

Current features include:

- revenue acceleration
- gross-margin momentum
- operating-margin momentum
- EPS acceleration
- cash-flow momentum
- inventory relief
- cycle state

Validation uses future returns only as an evaluation target, never as an input to the turnaround score.

Run:

~~~
python app/main.py --turnaround
~~~

---

## End-to-end research flow

~~~
1. Collect evidence
   └─ MOPS / MOEA / TSMC / TPCA / TrendForce public

2. Preserve point-in-time availability
   └─ period_date + published_at

3. Normalize evidence
   └─ signal × reliability × freshness

4. Deduplicate causal events
   └─ evidence_group

5. Infer demand / supply state
   └─ independent-chain confirmation

6. Map evidence into industry-specific drivers
   └─ ABF / Memory / Foundry / CCL

7. Build historical operating series
   └─ correlation-ready panel

8. Scan candidate lead-lag relations
   └─ Spearman / Pearson / lag / OOS

9. Validate candidates
   └─ rolling / cross-company / bootstrap / permutation / walk-forward / FDR

10. Promote only robust relations
    └─ validated_driver_registry.json

11. Attach validated empirical edge to industry model
    └─ no double-counting

12. Translate industry driver → product economics
    └─ Volume / ASP / Margin

13. Bridge product economics → company EPS

14. Detect fundamental inflection
    └─ Turnaround Radar

15. Compare with market expectations
    └─ planned Expectation Gap layer

16. Send research signal to invest_backtest
    └─ strategy / portfolio / risk validation
~~~

Detailed methodology:

- docs/FUNDAMENTAL_ALPHA_ARCHITECTURE.md

---

## Key commands

Main desktop app:

~~~
python app/main.py
~~~

Demand Evidence Lab:

~~~
python app/main.py --demand-evidence
~~~

Industry Driver Lab:

~~~
python app/main.py --industry-driver
~~~

Turnaround Radar:

~~~
python app/main.py --turnaround
~~~

Collection Progress:

~~~
python app/main.py --collection-progress
~~~

Correlation Lab:

~~~
python app/main.py --correlation
~~~

Run operating correlations:

~~~
python scripts/run_operating_correlations.py
~~~

Run robust driver validation:

~~~
python scripts/run_driver_validation.py
~~~

---

## Important data files

| Path | Purpose |
| --- | --- |
| data/company_master.csv | Company master |
| data/product_master.csv | Product master |
| data/company_product_relationships.csv | Company × product exposure |
| data/industry_driver_models.json | Industry equations and driver definitions |
| data/validated_driver_registry.json | Empirically validated driver relations |
| data/monthly_revenue.csv | Canonical company monthly revenue |
| data/quarterly_financials.csv | Canonical quarterly financials |
| data/evidence_observations_canonical.csv | Current canonical evidence snapshot |
| data/history/free_industry_history_panel.csv | Correlation-ready historical panel when restored from evidence-data |
| data/data_model_manifest.json | Dataset manifest |

Persistent history is stored on the evidence-data branch. Factor-validation history uses the separate factor-data branch.

---

## CI / research integrity

The repository uses GitHub Actions to check:

- Python tests
- parser behavior
- point-in-time guards
- history coverage
- operating correlation output
- validated-driver pipeline
- UI smoke tests
- screenshot artifacts
- full regression against existing features

Research principle:

> Fail closed.

If history is too short, publication time is unknown, a parser breaks, or a driver fails robustness gates, the system should say insufficient / candidate instead of manufacturing a confident result.

---

## Current limitations

- the free history panel is still short for true cross-cycle validation
- TrendForce public DRAM history is still accumulating
- some publication timestamps use conservative proxies
- validated operating relations are not yet calibrated into EPS sensitivities
- macro-regime segmentation is not yet wired into driver validation
- expectation-gap versus analyst consensus is still planned
- a validated driver is not the same as causal proof
- no research output should be interpreted as a buy/sell recommendation

---

## Near-term roadmap

1. Driver lifecycle
   - automatic revalidation
   - degradation / retirement status
   - regime-conditioned confidence

2. Industry Driver → Product Economics
   - calibrate Volume / ASP / Margin sensitivity
   - attach empirical lag / confidence to financial bridges

3. Product Economics → EPS
   - use product exposure and product earnings attribution
   - produce base / bull / bear earnings scenarios

4. Expectation Gap
   - compare internal EPS scenarios with consensus / market expectations

5. Cross-repo contracts
   - MarketRegimeV1
   - ResearchSignalV1
   - BacktestResultV1

6. Research automation
   - versioned research runs
   - reusable research skills
   - controlled AutoResearch loop against fixed point-in-time benchmarks

---

## Local setup

Python 3.11+ is recommended.

~~~
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
~~~

Windows PowerShell:

~~~
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
~~~

Launchers:

~~~
./run.sh
~~~

~~~
.\run.ps1
~~~

---

## Research philosophy

The platform should answer:

~~~
What changed?
↓
Which industry driver changed?
↓
Which product economics changed?
↓
Which companies are exposed?
↓
How much can revenue / margin / EPS change?
↓
Was this relationship historically robust?
↓
What did the market likely already price in?
~~~

The goal is not to create a model that sounds confident.

The goal is to create a research system where every important claim can be traced back to:

~~~
source
publication time
transform
historical evidence
validation result
model relation
company exposure
financial impact
~~~


## ABF indicator timing and sensitivity

The ABF reference model explicitly separates four concepts:

- **Indicator** — a dated observable metric.
- **Driver** — the economic state or mechanism inferred from indicators.
- **Sensitivity** — the empirical magnitude from a validated observable to a downstream operating metric.
- **Model** — the structural industry equations that route drivers through revenue, margin and EPS.

Timing is always **target-relative**:

- **Leading**: useful before the target is visible. Current validated example: TPCA PCB Revenue YoY leads the ABF revenue basket by 1 month.
- **Coincident**: confirms the current operating state. Current examples: 欣興 / 景碩 / 南電 monthly revenue YoY and the ABF revenue basket.
- **Lagging**: confirms financial propagation. Current examples: Gross Margin, Operating Margin and EPS relative to the original demand/revenue inflection.

The current real-data result makes an important distinction:

```text
Direction:
TPCA PCB Revenue ↑ -> future ABF Revenue ↑
= VALIDATED

Magnitude:
exact revenue beta
= CANDIDATE until chronological OOS magnitude validation passes
```

A driver score is never treated as a financial beta, and validated correlation is not added as a second copy of the same evidence.

Run:

```bash
python app/main.py --abf-research
```

The ABF Research Lab includes:
- Indicator Timing
- Revenue Sensitivity
- Driver ↔ Sensitivity ↔ Model
