# Fundamental Alpha Research Platform — Architecture & Methodology

## 1. Product thesis

The platform is designed around a fundamental operating thesis:

> Stocks are repriced after the market changes its expectation of future cash flow. The research advantage is to detect where profit pools are moving before the full effect appears in reported EPS.

The system does not begin with "predict tomorrow's stock price."

It begins with:

~~~
Demand / supply change
→ price / utilization / mix
→ product revenue / gross profit
→ company margin / EPS
→ expectation revision
→ valuation re-rating
~~~

This distinction drives the architecture.

## 2. Why three repositories

### chain_survey — research truth

Owns:

- evidence ingestion and provenance
- point-in-time research data
- industry models
- causal / structural hypotheses
- operating correlation
- robust driver validation
- product economics
- company earnings bridge
- turnaround / inflection
- expectation-gap research
- research-run registry

Question owned by this repo:

> Why do we think this company's fundamentals are changing?

### market-temperature-dashboard — market context

Owns:

- macro / liquidity / sentiment state
- regime classification
- market-level risk context
- point-in-time macro features

Target output: MarketRegimeV1.

Question owned by this repo:

> What market environment are we operating in?

### invest_backtest — strategy truth

Owns:

- signal consumption
- strategy construction
- walk-forward validation
- transaction costs
- portfolio construction
- position sizing
- risk management
- performance attribution
- Monte Carlo / bootstrap strategy robustness

Target output: BacktestResultV1.

Question owned by this repo:

> If we had acted on the research signal, would the strategy survive realistic implementation?

### Boundary rule

Do not duplicate the same business logic across repositories.

If a relation such as:

~~~
PCB Revenue YoY
→ ABF operating revenue
~~~

is learned and validated in chain_survey, invest_backtest should consume the resulting research signal rather than reimplement the fundamental logic.

## 3. Data architecture

### 3.1 Canonical business data

Examples:

- company master
- product master
- company × product relationships
- monthly revenue
- quarterly financials

These represent observable company fundamentals.

### 3.2 Evidence observations

Evidence is not equal to truth. It is a dated observation that can support or contradict a hypothesis.

Typical schema:

~~~
evidence_id
theme
dimension
chain
evidence_group
indicator
period_date
published_at
raw_value
raw_unit
signal
source_type
reliability
half_life_days
source
transform
transform_version
provenance
~~~

### 3.3 Point-in-time principle

The economic period and availability time are different.

Example:

~~~
August revenue
period_date = 2026-08-31

published on
published_at = 2026-09-10
~~~

A backtest evaluating 2026-09-09 must not see the August revenue.

Therefore:

~~~
eligible evidence
=
published_at <= evaluation_as_of_date
~~~

### 3.4 Conservative timestamps

When exact publication time is unavailable, use a conservative proxy.

Example:

- MOPS historical monthly revenue uses the regulatory filing deadline as a conservative knowledge-time proxy.

This can delay information, but it avoids falsely assuming earlier availability.

False delay is preferable to look-ahead leakage.

## 4. Evidence quality model

### 4.1 Effective evidence

~~~
Effective Evidence
=
Normalized Signal
× Reliability
× Freshness
~~~

### 4.2 Reliability

Reliability expresses source confidence, not directional strength.

Examples:

- government statistic
- regulatory filing
- company actual
- company guidance
- industry association
- industry research public
- supplier commentary
- channel check
- anonymous news

Reliability priors should eventually be empirically calibrated.

### 4.3 Freshness

Freshness decays exponentially.

Different evidence should use different half-lives.

Examples:

- daily spot price: short
- capacity expansion: long
- quarterly revenue confirmation: medium

### 4.4 Deduplication

Multiple reports can describe one economic event.

Without deduplication:

~~~
one capex announcement
→ 5 articles
→ false 5× confidence
~~~

The system groups these observations by evidence_group.

Independent chain confirmation is valuable. Repeated narrative is not.

## 5. Demand inference

Demand is treated as a latent state inferred from evidence.

Dimensions:

1. Buyer Commitment
2. Orders / Backlog
3. Physical Throughput
4. Market Tightness
5. Financial Confirmation

The engine reports:

~~~
theme
score
state
confidence
independent chains
positive evidence
conflicting evidence
dimension scores
~~~

The demand engine is intentionally generic.

Industry-specific meaning belongs in the Industry Driver Model.

## 6. Industry Driver Model

### 6.1 Structural model

ABF:

~~~
Demand
=
Chip shipment
× Substrate area per chip
× Complexity

Revenue
=
Shipment × ASP

GM
=
f(ASP, utilization, mix, yield, material cost)
~~~

Memory:

~~~
Bit demand
=
Device shipment × content per device

Bit supply
=
Wafer capacity × yield × bits per wafer

Revenue
=
Bit shipment × ASP / bit
~~~

Foundry:

~~~
Wafer demand
=
Chip units × die size / dies per wafer × node mix
~~~

CCL / PCB:

~~~
Material demand
=
System shipment
× Board area
× Layer count
× High-speed material content
~~~

### 6.2 Relation types

The architecture distinguishes:

~~~
ACCOUNTING_IDENTITY
STRUCTURAL_RELATION
EMPIRICAL_RELATION
~~~

Accounting identity:

~~~
Revenue = Volume × ASP
~~~

Structural relation:

~~~
AI accelerator shipment
→ ABF demand
~~~

Empirical relation:

~~~
TPCA PCB Revenue YoY
→ ABF revenue basket
lead 1M
ρ ≈ +0.58
~~~

### 6.3 Evidence status

A model relation can carry:

~~~
OBSERVED
EMPIRICALLY_LINKED
CAUSAL_HYPOTHESIS
~~~

A structural hypothesis can exist before empirical validation.

The UI should make this distinction explicit.

## 7. Historical panel and correlation

### 7.1 Point-in-time comes first

Sequence:

~~~
raw source
→ publication timestamp
→ point-in-time history
→ correlation
~~~

Do not start from a today's cleaned historical database and assume every value was historically knowable.

### 7.2 Lead-lag convention

Positive lag means the feature leads the target.

~~~
lag = +1M

Feature at month t
→ Target at month t+1
~~~

### 7.3 Current ABF targets

- 欣興 revenue YoY
- 景碩 revenue YoY
- 南電 revenue YoY
- median ABF basket

The basket reduces idiosyncratic company noise.

## 8. Why simple correlation is not enough

If many feature × lag combinations are scanned, some high correlations appear by chance.

Therefore:

~~~
Candidate discovery
≠
Driver validation
~~~

The pipeline does not use "highest correlation wins."

## 9. Validated Driver Pipeline

### 9.1 Sample-size gate

Insufficient history cannot become a validated driver.

TrendForce public DRAM data currently fails correlation eligibility because append-only history is still short.

### 9.2 Chronological OOS

The final part of the time series is treated as unseen test data.

A relation must preserve direction and meaningful magnitude outside the fit period.

### 9.3 Rolling stability

Current windows:

- 12 months
- 18 months

The pipeline measures how often rolling correlation preserves the full-sample direction.

### 9.4 Cross-company generalization

If a hypothesis is industry-wide, it should not work only for one company.

Current ABF companies:

- 欣興
- 景碩
- 南電

### 9.5 Moving-block bootstrap

Ordinary iid bootstrap breaks time-series dependence.

Moving blocks preserve some local autocorrelation and generate a 95% correlation interval.

### 9.6 Block permutation

The target series is permuted by blocks rather than single observations.

Question:

> How often can a relation at least this strong appear after temporal alignment is disrupted while preserving some local structure?

### 9.7 Multiple-testing correction

Benjamini-Hochberg FDR is applied to permutation p-values to reduce false discoveries from data snooping.

### 9.8 Nested walk-forward

Bad workflow:

~~~
See all history
→ choose lag 1M
→ report lag 1M OOS
~~~

Correct workflow:

~~~
Train window
→ choose best lag using train only
→ evaluate next unseen window

Expand train
→ choose lag again
→ evaluate next unseen window
~~~

The test period never influences lag selection.

## 10. Current validated relation

First full-pipeline validated driver:

~~~
TPCA PCB Revenue YoY
→ ABF Revenue YoY Basket
lead = 1 month
~~~

Validation snapshot:

~~~
sample_size                 31
spearman                 +0.5801
pearson                  +0.6344
chronological_oos        +0.5152
rolling_sign_share        0.8529
cross_company_sign_share  1.0000
walk_forward_oos_median  +0.8000
walk_forward_sign_share   1.0000
bootstrap_ci_low         +0.0802
bootstrap_ci_high        +0.7944
permutation_p             0.0070
fdr_q                     0.0420
gates                      6 / 6
status                    VALIDATED
~~~

Stored in:

~~~
data/validated_driver_registry.json
~~~

It enters the model because it passed all current robustness gates and FDR correction.

It does not become causal truth. Possible alternative explanations still include common electronics cycles, omitted macro variables, the recent AI infrastructure cycle, and limited history.

## 11. Double-counting rule

TPCA PCB Revenue already enters the Evidence Engine.

Adding a second validated-driver score for the same observation would count the same information twice.

Correct design:

~~~
Evidence Engine
→ signal strength

Validated Driver Registry
→ relation status / lag / empirical confidence
~~~

Validation upgrades metadata and interpretation.

It does not duplicate the observation.

## 12. Validated Driver Registry

Registry role:

~~~
historical validation output
→ durable model contract
~~~

Entry fields include:

~~~
driver_id
status
industry_model_id
target_driver_id
source_metric
target_metric
direction
expected_lag
relation_type
mechanism
validation metrics
~~~

Only VALIDATED / PRODUCTION relations can be loaded into the Industry Driver Model.

CANDIDATE relations remain research output only.

## 13. ResearchRunV1

A research run records:

~~~
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

This makes results reproducible.

Six months later, "correlation = 0.58" is not enough. We need to know which data snapshot, code, lag search space, validation rules, companies, and multiple-testing correction produced it.

## 14. Product economics

Target bridge:

~~~
Industry Driver
      ↓
Product Volume
Product ASP
Product Cost / GM
      ↓
Product Revenue / GP
      ↓
Company Revenue / OI
      ↓
Net Income / EPS
~~~

The current product engine supports scenario changes in:

- volume
- ASP
- gross margin

and multi-product earnings contribution.

The next calibration problem is:

> How much does a validated industry driver move Volume / ASP / Margin?

That sensitivity must also be empirically tested.

## 15. Turnaround logic

Turnaround is not:

~~~
stock price fell a lot
~~~

It is an operating inflection.

Current feature families:

~~~
Revenue acceleration
Gross-margin momentum
Operating-margin momentum
EPS acceleration
Cash-flow momentum
Inventory relief
Cycle state
~~~

Target sequence:

~~~
Supply / demand inflection
→ Price / utilization inflection
→ Revenue inflection
→ Margin inflection
→ EPS inflection
→ Consensus revision
→ Valuation re-rating
~~~

## 16. Current UI surfaces

### Demand Evidence Lab

- evidence quality
- deduplication
- conflicting evidence
- independent-chain breadth

### Industry Driver Lab

- industry states
- industry equations
- Volume / ASP / Margin bridge
- company exposure
- empirical validation status

Driver rows expose:

~~~
Evidence Status
Empirical Lag
Empirical ρ
~~~

### Turnaround Radar

- operating inflection
- company state
- forward validation statistics

### Collection Progress

- persistent collection health

## 17. CI is part of the research method

CI is not only software quality control.

Examples:

Parser test fails:
- interpretation: source format may have changed
- action: block the pipeline

Point-in-time guard fails:
- interpretation: possible look-ahead
- action: block research output

History too short:
- interpretation: insufficient sample
- action: exclude from correlation ranking

Driver fails walk-forward:
- interpretation: relation may be in-sample or regime-specific
- action: keep CANDIDATE

Green CI therefore has research meaning.

## 18. What should be automated next

### 18.1 Driver lifecycle

Future states:

~~~
VALIDATED
→ PRODUCTION
→ DEGRADED
→ RETIRED
~~~

Possible retirement triggers:

- rolling sign share drops
- OOS correlation decays
- recent windows flip direction
- structural mechanism changes
- source methodology changes

### 18.2 Regime-conditioned drivers

Future contract:

~~~
driver
+
MarketRegimeV1
→ conditional driver confidence
~~~

This should be measured, not assumed.

### 18.3 Sensitivity calibration

After a driver is validated:

~~~
Δ driver
→ Δ volume
→ Δ ASP
→ Δ GM
→ Δ EPS
~~~

This converts directional usefulness into financial usefulness.

### 18.4 Expectation Gap

Final fundamental alpha question:

~~~
Our point-in-time EPS expectation
-
Market consensus expectation
=
Expectation Gap
~~~

Fundamental improvement alone is not enough if the market already expects more.

## 19. Research workflow example

Question:

> Does PCB industry momentum lead ABF substrate company fundamentals?

Step 1:
- target = ABF basket revenue YoY

Step 2:
- candidate = TPCA PCB Revenue YoY

Step 3:
- enforce publication time

Step 4:
- scan lag 0–6M

Step 5:
- rolling stability
- cross-company
- bootstrap
- permutation
- FDR
- nested walk-forward

Step 6:
- register only if gates pass

Step 7:
- attach validated relation to ic_substrate_abf_bt / end_demand

Step 8:
- do not double-count

Step 9:
- estimate whether the validated driver predicts ABF revenue acceleration, GM, and EPS

That becomes the next sensitivity-calibration study.

## 20. Design principles

### Point-in-time before correlation

A statistically perfect relationship built on look-ahead data is useless.

### Correlation before rule

Do not turn an intuition into a production rule before historical validation.

### Validation before weight tuning

Do not optimize a score weight when the relation itself is unstable.

### Mechanism + statistics

Statistics without mechanism can be spurious.

Mechanism without empirical evidence can be storytelling.

We want both.

### Fail closed

Prefer:

~~~
insufficient data
candidate
mixed evidence
low confidence
~~~

over fake precision.

### No double-counting

Multiple observations from the same causal chain are not automatically independent signals.

### Reproducible research

Every important claim should trace to:

~~~
code SHA
data SHA
source
publication time
transform
methodology
result
~~~

### Human decision, machine discipline

The system should improve evidence quality, consistency, auditability, and research speed.

It should not hide uncertainty or make the investment decision for the user.

## 21. Recommended next milestones

### Milestone A — complete driver lifecycle

- persist research-run history
- automatic revalidation
- degradation / retirement status
- regime-conditioned confidence

### Milestone B — sensitivity calibration

For validated drivers:

~~~
driver change
→ revenue change
→ GM change
→ EPS change
~~~

### Milestone C — Expectation Gap

~~~
internal EPS scenario
vs
consensus
~~~

### Milestone D — cross-repo contracts

Formalize:

~~~
MarketRegimeV1
ResearchSignalV1
BacktestResultV1
~~~

### Milestone E — controlled AutoResearch

An agent may propose:

- transformation
- lag
- target
- interaction
- regime split

but each proposal must pass the same fixed point-in-time benchmark.

The agent may generate hypotheses. It may not redefine success after seeing the test result.

## 22. End-state

~~~
Evidence
  ↓
Demand / Supply State
  ↓
Validated Industry Driver
  ↓
Product Economics
  ↓
Company Revenue / Margin / EPS
  ↓
Turnaround
  ↓
Expectation Gap
  ↓
Valuation
  ↓
Strategy Validation
~~~

Every important edge should carry:

~~~
source
published_at
relation_type
expected_lag
historical correlation
OOS result
generalization
confidence
status
research_run_id
~~~

That is the difference between a dashboard containing interesting numbers and a reusable fundamental research system.
