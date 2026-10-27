# ABF financial calibration: source reconciliation and company validation

The user confirmed on 2026-10-26 that the next task is to continue acquiring data
and calibrating ABF, rather than merely explaining the existing limitations.
`chain_survey` remains the sole research product. Finance-industry expansion waits.

## Scope

Complete the missing company-specific Revenue→GM validation and ingest newly
verified primary financial/product/downside evidence. The minimum analysis key
remains Company × ABF. Company-total financial data remain explicitly named proxies.
No product forecast can be inferred from pooled company statistics.

The work has three independently inspectable outputs:

1. Primary-document observations with actual measurement scope, column periods,
   units, precision, document/page, publication bounds and acquisition time.
2. A deterministic company-specific margin audit, including independent upside and
   downside families, uncertainty, chronological holdouts and unavailable states.
3. The same audit and source-reconciliation progress in the application and offline
   report, with full sample references distinguished from forecasting qualification.

## Financial input verification

Reviewed quarterly financial records retain company, quarter end, revenue, gross
profit, unit scale, standalone/YTD basis, consolidation scope, source URL/page,
publication/retrieval timestamps, precision and derivation dependencies. A Q1
derived from H1 minus Q2 requires both columns in the same source and remains
DERIVED. Comparative prior-year columns inherit the current document's knowledge
time; they do not establish the original filing vintage.

Reconcile amounts against provider rows using only documented rounding tolerance.
An exact match, a match to rounded disclosure, and a mismatch are different states.
Unknown/mismatching accounting basis cannot become verified by assigning a flag.
The value provider and the primary verification source remain separately recorded.
Acquisition bounds cannot be silently replaced by historical filing dates.

## Margin audit

Predeclare two revenue growth features (`monthly_revenue_3m_yoy`, `revenue_yoy`),
two margin-change targets (`gross_margin_qoq`, `gross_margin_yoy_delta`) and lags
0, 1 and 2 calendar quarters for each of three companies. Upside and downside are
selected independently by the sign of the revenue-growth feature. The family
contains 36 hypotheses per side, including missing comparisons with p=1.

Ratios are converted to percentage points before regression. A descriptive slope
is ESTIMATED and never an actual measurement. Its name and units must distinguish
it from `forecast_beta`, which remains null whenever any forecasting gate fails.
Lag 0 is coincident; a positive lag is only an early-warning candidate when the
feature was known before the target observation ended.

Use fixed expanding chronological folds, purge unavailable training labels, and
require sufficient nonconstant train/test observations before reporting a fold as
validated. A test-subset correlation with no usable training set is not validated
OOS evidence. Bootstrap/permutation blocks stop at calendar-quarter gaps. Company
sign agreement always uses three companies as the denominator. Never select the
lag, feature or scenario based on holdout performance.

Every sample retains feature and target periods, source URLs, accounting/PIT
verification, observation_date, release_date, available_at and signal_generated_at.
Knowledge is bounded by release, existing availability and acquisition metadata.
Missing publication timestamps stay null. No eligible ABF product relationship
means no ABF forecast coefficient, even when descriptive company correlations are
large. Statistical, source, accounting, PIT and product-attribution failures are
reported separately.

## Downside evidence

Official measured product data, dated qualitative management statements and
forward guidance are distinct records. Do not convert qualitative utilization
into an invented percentage. Do not convert a forecast or IC-substrate aggregate
into ABF actuals. New facts improve evidence coverage without automatically
satisfying a historical calibration requirement.

## Acceptance

Reconciliation and margin tests cover incompatible units/periods, missing or
future knowledge, conflicting records, calendar gaps, no-train holdouts, separate
FDR families, fixed company denominator and null forecast coefficients on proxy
data. Review real source pages and resulting plots. Run the full unit/contract/UI
suite and current-head Actions. Deliver updated report, source audit and bundle.
Report the actual remaining research limits without equating software completion
with an identified product-level economic relationship.
