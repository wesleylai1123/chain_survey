# ABF margin calibration implementation plan

> Execute the approved ABF continuation in the current feature branch, with
> independent source audits and a separate code review before integration.

**Goal:** Complete company-specific Revenue→GM evidence and source reconciliation,
without manufacturing ABF-only actuals or historical pipeline knowledge.

**Architecture:** Reviewed financial-document records reconcile a factor snapshot;
a pure margin validation module produces deterministic Company × ABF comparisons.
The existing semantics report/handoff remains the authority consumed by both UIs.

**Tech stack:** Python, pandas/numpy/scipy, unittest, existing Tk/HTML/SVG, Actions.

### Task 1: Primary evidence and financial reconciliation

Files: `data/abf_quarterly_financial_evidence.json`,
`core/abf_financial_evidence.py`, `tests/test_abf_financial_evidence.py`, and
new independently verified records in `data/abf_company_research_evidence.json`.

- [x] Acquire primary quarterly columns and source/date/precision metadata. Record
  only inspected values and dependencies. Compare with current provider values.
- [x] Write and run a failing reconciliation test with a wrong quarterly amount:

```python
result = reconcile_financial_evidence(panel, reviewed, as_of=cutoff)
assert result.iloc[0]['accounting_basis'] == 'UNKNOWN'
assert result.iloc[0]['financial_value_verification'] == 'MISMATCH'
```

- [x] Implement `reconcile_financial_evidence(panel, reviewed, *, as_of)`; only a
  compatible same-company standalone/consolidated record verifies basis. Preserve
  provider provenance and acquisition time; add primary source/precision/status.
- [x] Verify exact/rounded matches, mismatch, future evidence, wrong company,
  YTD, unknown publication and conflicting IDs with focused tests.

### Task 2: Company-specific margin audit

Files: `core/abf_margin_validation.py`, `tests/test_abf_margin_validation.py`,
`scripts/run_abf_semantics_validation.py`.

- [x] Write and run a failing test proving that current acquisition bounds prevent
  a historical training set from being treated as OOS validation:

```python
audit = validate_margin_transmission(panel, as_of=cutoff, iterations=39)
assert all(r['forecast_beta'] is None for r in audit['comparisons'])
assert all(not r['gates']['oos_stability'] for r in audit['comparisons'])
```

- [x] Implement all 72 predeclared company/scenario/feature/target/lag combinations,
  with percentage-point units, full sample references, quarter-contiguous
  resampling, fixed chronological purged folds and 36-test FDR families per side.
- [x] Test missing sources/periods, unavailable states, calendar alignment, no-train
  folds, constant samples, deterministic resampling, fixed denominator and proxy
  rejection. Four timestamps and dependencies remain attached to every sample.
- [x] Replace the handoff's unvalidated company-statistics placeholder with each
  company's own audit rows. Keep pooled exploration under a separate reference.

### Task 3: Research surface and final verification

Files: `core/abf_company_survey.py`, `core/abf_company_survey_html.py`,
`app/abf_company_survey_view.py`, relevant tests/workflows and documentation.

- [x] Include primary verification coverage and company margin audit in the common
  report. Show descriptive estimates, forecasting gates, sources and missing data
  as distinct fields; a rejected relationship cannot receive a forecast beta.
- [x] Run focused then full tests, four contract fixtures, native UI smoke and
  browser checks; inspect current-version screenshots.
- [x] Obtain independent spec and quality review and fix material issues.
- [ ] Publish the same feature PR, verify all Actions for its exact head, and
  regenerate the evidence bundle. The post-commit result is recorded in
  `artifacts/abf-company-survey-acceptance.json` together with its exact revision;
  this source plan does not predeclare a future CI outcome.
