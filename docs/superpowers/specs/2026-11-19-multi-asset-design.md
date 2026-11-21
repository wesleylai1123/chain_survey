# Multi-asset and ETF research framework

## Inventory (2026-11-19)

- Main product: `chain_survey`, baseline `39c17f2`, Python/Tk desktop, audited ABF evidence, indicator taxonomy, correlation/OOS, driver, sensitivity and model layers. Existing research signals are JSON artifacts. No cross-repository Python imports are permitted by the existing contracts.
- Validation service: `invest_backtest`, baseline `09a6b8dfbc5e9b3e2057042af46e54c42bd18309`, Backtrader/Qt plus a headless frozen-input stack. Existing strict V1 research/regime/backtest contracts remain unchanged.
- Regime service: `market-temperature-dashboard`, baseline `73a48a09be3c9665e0becc02d604ee7392d00717`, has an offline `MarketRegimeV1` exporter with source freshness. Stale source values cannot become fresh through this integration.
- Missing: common instrument identity, ETF distributions/holdings/benchmark history, explicit return basis, base-currency research, and a comparative UI.

## Approaches

1. Recommended: an additive JSON research contract; isolated numerical service in invest_backtest; main-product adapters, evidence bridge and comparative Tk UI. Consume existing regime exports. This preserves repo ownership and ABF behavior while enabling offline replay.
2. All analytics in chain_survey: simpler launch but duplicates performance responsibilities and makes later portfolio validation harder.
3. New hosted API/data warehouse: useful later, but adds deployment, credentials and availability dependencies before data integrity is proven.

## Design

Use `MultiAssetResearchV1` requests and `MultiAssetResultV1` responses, exchanged through a headless CLI subprocess, never shared `core` imports. chain_survey owns the instrument/request schema; invest_backtest owns metrics/results. Requests include explicit cutoff, observation interval, return basis, objectives, base currency, cost assumptions, and source lineage. Local files are the first adapter; additional providers implement the same normalized input contract. No live feed is silently presumed available.

Instrument identity includes asset type (stock, ETF, FX, benchmark), exchange, quote currency, domicile, ETF management style/benchmark, and FX base/quote currencies. Observations contain economic time, published_at, acquired_at, source URL and snapshot identity. Availability is max(published_at, acquired_at); unknown times/values are visible exclusions. Historical revisions retain their vintage. No forward fill or interpolation manufactures returns, distributions, holdings, FX rates, or regime labels.

Return series distinguish split-adjusted prices plus complete explicit distributions, and vendor total-return indices. Adjusted total returns never receive dividends twice. Incomplete corporate-action/distribution coverage blocks total-return claims. Returns, benchmark comparison and cross-asset correlations use common declared intervals and currency; gaps remain gaps. FX is quoted as units of reporting currency per local currency, with explicit inversion. Cash FX uses pay-date rates. Unlevered spot FX return excludes carry and trading leverage.

The service calculates total return, drawdown, annualized volatility, Sharpe/Sortino with explicit risk-free assumptions, rolling compounded returns, passive tracking difference/error and point-in-time expense ratio, active return/CAPM alpha/information ratio, trailing paid distribution yield, payout CV/cut frequency and tax/fee-aware cash flow when inputs exist. Expense ratios already reflected in NAV are displayed, never deducted twice. Accumulation and income outputs distinguish reinvested total return from paid cash and terminal wealth. Missing tax rules produce unknown net cash, not zero taxes. No personalized tax rates are invented.

Cross-asset research reports common samples, chronological train/OOS correlations, regime-conditioned correlations from available non-stale exports, and no automatic driver promotion. Holdings snapshots support partial coverage, holdings/sector/factor/currency weights and unknown residual. ETF quote currency does not imply underlying currency exposure. A main-product evidence bridge attaches target-relative leading/coincident/lagging indicator rows, independent upside/downside evidence, and existing driver/sensitivity/model references without weighting the same evidence twice or treating exposure as an EPS beta.

The UI adds a separate Multi-asset Research Lab with file loading, objective and reporting currency selection, comparable metrics, cash-flow table, rolling returns, correlation/OOS/regime, exposures, evidence, and provenance/gaps. Initial launch has a clear no-data state. Synthetic fixtures are explicitly TEST ONLY and confined to tests/screenshots. Existing ABF routes and calculations remain intact.

## Verification and acceptance

Write failing arithmetic and integrity tests first: dividend accounting, adjusted-price double counting, pay vs ex date, FX direction, future vintages, missing coverage, constant series, gaps, benchmark alignment, tax unknowns, OOS splits, look-through residuals and independent evidence. Run baseline and final ABF/full regression, existing JSON contract suites and service tests. Add deterministic offline CI with peer checkout pinned to a reviewed service commit and UI screenshot artifacts. Inspect rendered populated and missing-data states. Open feature PRs; inspect every PR check and resolve failures without weakening ABF gates. Do not merge or deploy.

## Data-source limits

Production adapters require licensed/verifiable split-adjusted prices, total-return benchmarks, ex/pay-date distributions and revision history. Issuer holdings may be partial, delayed or opaque. Fees need effective dates; tax depends on residency/account/treaty and payout classification. Historical source publication times cannot be inferred from today's download. Unavailable inputs stay unavailable, with source gaps listed in the result and UI.
