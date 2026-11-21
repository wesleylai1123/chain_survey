# ETF NAV and reference indices implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task with specification review followed by quality review.

**Goal:** Capture official ETF NAV and return indices, show exact-date premium/discount and source coverage, preserving all raw-price restrictions.

**Architecture:** Main-product parsers and context helpers feed an optional versioned immutable capture. The existing JSON numerical service handles two independent total-return reference instruments. A separate UI tab displays NAV facts and coverage.

**Tech Stack:** Python, requests, csv/json, unittest, Tk/ttk, existing JSON Schema and subprocess service.

Approved spec: `docs/superpowers/specs/2026-11-21-etf-nav-benchmark-design.md`. Continue existing PRs; no merge/deploy. Work in the isolated `feature/etf-nav-context` worktree and fast-forward the existing product feature branch after review. Explicit peer environment paths are required in local tests because this worktree is outside the three sibling repos.

## Task 1: Strict source parsers and context calculations

Files: new `core/multi_asset/official_context.py`, `tests/test_multi_asset_official_context.py`, actual source fixtures under `tests/fixtures/taiwan_etf_context/` with provenance. Existing source-audit originals are under `artifacts/source-audit-2026-11-21/`.

- [x] Write failing tests using `parse_nav(raw, metadata, symbols)` and `parse_index(raw, metadata, kind)`; run `python -m unittest discover -s tests -p test_multi_asset_official_context.py -v`, expect absent module/functions.
- [x] Implement three context source definitions and two reference instrument definitions. NAV rows use `instrument_id`, `period`, `nav`, `currency` and standard provenance. Index rows use `instrument_id`, `period`, `value`, optional `price_index` and provenance. Preserve TWD/leading-zero identity, nulls and real source times. Fail on drift, conflicts, bad dates/currencies/numbers and future dates. Support only documented seven-digit ROC compact index dates.
- [x] Add failing exact-date/cutoff/missing/currency tests for `valuation_rows(request)` and `reference_rows(request)`. Context is in `adapter_lineage.etf_context = {schema_version: '1.0.0', nav_observations: [...], index_observations: [...]}`. Valuation output fields: instrument_id, period, nav, close, currency, premium_discount, reason, nav_source_url, price_source_url. Reference output includes instrument_id, supplied_start/end, available_count, grid_count, reason and source_url.
- [x] Implement `premium_discount = close/nav-1` only for positive same-date in-window native-currency values available at cutoff. Report all source NAV rows with reasons. Reference coverage counts unique usable dates on the request grid; source ranges include actual supplied dates. Old snapshots return empty context. Run new tests and old official-source tests, inspect actual fixture provenance, commit. Independent specification and quality reviews passed after boundary corrections (38 context tests plus 12 existing source tests).

## Task 2: Versioned optional capture

Files: modify `core/multi_asset/official_capture.py`, `scripts/collect_taiwan_official_data.py`; new `tests/test_multi_asset_context_capture.py`.

- [x] Write failing tests for `capture_official_data(..., include_etf_context=True)` and old exact replay. Capture 1.1.0/parser `taiwan-official-1.1.0` adds three context sources; old 1.0.0/parser 1.0.1 uses exactly the old source set and request bytes. Run context capture tests to see the unsupported keyword/version failure.
- [x] Dispatch source identities/parsers by the allowlisted version. Freeze two reference instrument definitions in the new manifest. Validate those definitions on replay. Build the old request from only original sources, then append two independent reference instruments and in-grid index observations with the unchanged 1.1.0 request schema. Store NAV/all supplied index context in adapter_lineage; keep every ETF benchmark_id null. Extend capture signatures/CLI with the explicit opt-in flag and preserve old defaults.
- [x] Add rejection tests for mixed versions, metadata/source/hash/request tampering, source failures/latest-good protection and partial-month coverage. Run both capture suites and exact original frozen replay, commit.

## Task 3: NAV and reference UI

Files: new `app/etf_context_view.py`, `tests/test_multi_asset_context_ui.py`; modify `app/multi_asset_lab.py`, `app/official_data_view.py`.

- [x] Write failing tests for appended ninth tab, exact-date valuations, missing/cutoff/out-of-window states, reference coverage and old-capture explanatory state. Run `python -m unittest discover -s tests -p test_multi_asset_context_ui.py -v` to prove absence.
- [x] Implement the new 「淨值與基準」 view using Task 1 helpers; source URLs, date/currency and ratios remain visible. Add the opted-in checkbox to source dialog, pass a plain boolean to the worker, and preserve generation/stale/failure behavior. Integrate clear/render calls for loading, settings changes and engine failure. Preserve existing tab indices and controls. Restrict the existing raw-price view to ETF/FX observations and plots, so total-return reference indices cannot be mislabeled as unadjusted prices. Include temporarily invalid typed cutoffs as visible unavailable states. Run all UI tests, commit.

## Task 4: Real capture, integration and delivery verification

Files: new `scripts/taiwan_etf_context_ui_smoke.py`, context capture fixture; modify `tests/test_multi_asset_integration.py`, `.gitattributes`, `.github/workflows/multi-asset.yml`, `docs/taiwan-official-data.md`, README.

- [ ] Use the new CLI to capture 2026-11-02 through 2026-11-20 with context. Save exact originals as the sourced frozen fixture, then compute and retain a service result. Write failing subprocess tests asserting five identities, raw ETF nulls, exact index ratio returns and both contract copies. Run the targeted tests before implementing missing integration behavior.
- [ ] Implement offline UI smoke for actual populated facts, exact-date missing close, older out-of-window NAV and old snapshot states. Mark test mutations explicitly. Add frozen replay/UI CI steps and upload screenshots; keep original ABF jobs. Document opt-in CLI, source dates, benchmark purpose and remaining adjustment/tax gaps. Run focused tests/contracts and inspect images, commit.
- [ ] Independent final spec/quality review, complete main/engine/market regression, diff checks, fast-forward existing feature branch, update fixed private-CI producer SHA and PR descriptions, push both PRs. Wait for all current-head automatic checks and inspect uploaded current-head UI artifacts. Deliver exact file lists, counts, usage and remaining data gaps.
