# Multi-asset Research Implementation Plan

> For agentic workers: use subagent-driven-development for the isolated numerical service and independent reviews; controller integrates the main product. Test each behavior before implementation.

**Goal:** Add a reproducible stock/ETF/FX comparative research workflow without changing ABF semantics.
**Architecture:** Versioned JSON request/result, a headless invest_backtest CLI, chain_survey normalized adapters and evidence bridge, existing MarketRegimeV1 inputs.
**Stack:** Python, pandas/numpy, jsonschema, Tk/ttk, unittest/pytest. No new live feed or hosted service dependency.

## Task 1 — Freeze interfaces and baseline

- [x] Inspect three default branches, contracts, ABF entry points and workflow checks.
- [x] Record the approved design in `docs/superpowers/specs/2026-11-19-multi-asset-design.md`.
- [ ] Run existing suites with writable local temporary paths; save baseline logs outside versioned code.
- [ ] Define `docs/multi-asset-contract.md` and canonical `contracts/multi-asset/v1/schema.json` before producer/consumer implementations diverge.

## Task 2 — Numerical service (invest_backtest)

Files: `core/multi_asset/{validation,returns,metrics,research}.py`, `scripts/run_multi_asset_research.py`, `tests/test_multi_asset_research.py`, consumer schema snapshot, offline CI and documentation.

- [ ] Write arithmetic/integrity tests from the shared contract: dividend reinvestment vs paid cash; unknown taxes; FX direction; future acquisition exclusion; absent prices; benchmark matching; no adjusted-price double counting; payout dates; rolling windows; constant series and chronological OOS.
- [ ] Run tests red, implement the smallest isolated service, run green.
- [ ] CLI accepts `--input REQUEST --output RESULT`; writes deterministic JSON with `allow_nan=False`. Invalid requests exit nonzero without overwriting existing result.
- [ ] Results include instruments, metrics with explicit unavailable reasons, return/cash series, correlations/OOS/regime, input SHA256 and methodology.
- [ ] Run full existing engine suite and V1 contracts; commit only new service files, documentation and CI.

## Task 3 — Main-product adapters and research context

Files: `core/multi_asset/{adapters,service,context}.py`, canonical schema, `tests/test_multi_asset_adapters.py`.

- [ ] Test unknown identity, timestamp validation, strict missing values, duplicate vintages, schema incompatibility and service failure before implementation.
- [ ] Support normalized JSON and CSV bundle adapters that retain exact file hashes and never invent publication times.
- [ ] Launch service by explicit checkout path/`INVEST_BACKTEST_REPO`, use argument arrays and timeout, validate result contract and input hash.
- [ ] Bridge ETF holdings into security/sector/factor/currency exposures, compute unknown residual, reject oversized/duplicate weight sets and future snapshots.
- [ ] Attach existing indicator taxonomy and independent upside/downside records by declared target/driver/model. Exposure never supplies an invented sensitivity.

## Task 4 — Comparative UI and CLI

Files: `app/multi_asset_lab.py`, additive routes in `app/main.py` and launch button in `app/gui_app.py`, `scripts/run_multi_asset_research.py`, `tests/test_multi_asset_ui.py`, `scripts/multi_asset_ui_smoke.py`.

- [ ] Test empty state, objective switching, result rendering, file failure and entry route.
- [ ] Add tabs for comparison, cash, rolling returns, correlation/regime, exposures, evidence and data quality. Show base currency, date range, input SHA and assumptions.
- [ ] Provide input loading and engine checkout selection; expensive work executes outside Tk event handling.
- [ ] Empty default has no fabricated quotes. Tests create visibly labeled synthetic fixtures only.
- [ ] Render/inspect populated, income and missing-data screenshots with the actual service result.

## Task 5 — Integration and regressions

- [ ] Add `.github/workflows/multi-asset.yml` with pinned engine checkout and deterministic offline tests, request/result artifacts and Tk screenshots.
- [ ] Keep all ABF and old V1 contract checks intact. Run full regression, not only new tests.
- [ ] Run existing market regime suite and consume a real exporter result in integration tests, retaining stale flags.
- [ ] Request spec review, resolve findings, then request quality review and resolve findings.

## Task 6 — PR delivery

- [ ] Commit/push feature branches and open reviewable PRs (no merge/deployment).
- [ ] Inspect every check on current heads; diagnose failures and rerun only relevant failures.
- [ ] Deliver PR links, changed file groups, exact test outcomes, screenshots, launch steps and outstanding provider data gaps.
