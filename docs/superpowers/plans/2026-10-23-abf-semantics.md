# ABF semantics and independent validation

**Goal:** Continue chain_survey as the sole research product, with ABF as the reference Company × Product slice.

**Design:** Add a versioned JSON semantics registry and signal schema. YoY is already a change measure; LEVEL means identity of that measure, while CHANGE means its calendar-adjacent percentage-point difference. Never infer ABF product revenue from consolidated company revenue. Keep proxy, accounting basis, return basis, evidence status and validation eligibility separate. Unknown provenance blocks eligibility. All generated observations carry observation_date, release_date, available_at and signal_generated_at; null release dates remain explicit and block eligibility.

Use chronological splits and label-availability purging, per-company results, predeclared transform comparisons and scenario-specific statistical families. Upside and downside own their sample lineage, bootstrap, permutation, OOS and company sign evidence. No transform is selected using holdout performance. Industry and company-total proxies are support-only even when statistically strong. Revenue → GM remains a calibration candidate until product-level evidence supports it.

**Approach:** Extend the current ABF lab with an audited comparison tab rather than replacing research workflows or creating a second product. Existing exploratory scans remain identifiable as legacy exploration. Publish machine-readable reports and an HTML review artifact from the same engine shown by the UI.

- [ ] Establish clean baseline and restore persisted research inputs.
- [ ] Add failing tests for semantic distinctions, all four timestamps, missing and future evidence, revisions, calendar gaps and Company × Product scope.
- [ ] Implement strict semantics schema and provenance-preserving normalization.
- [ ] Add failing tests for transform comparison, independent sides, chronological purging, expected negative relations and missing-company agreement.
- [ ] Implement per-company comparison, fixed holdout and multiple OOS folds, bootstrap/permutation and scenario-family FDR. Retain exact used rows and input hashes.
- [ ] Add Revenue → GM calendar alignment and missing-PIT regression tests; implement conservative calibration handoff.
- [ ] Integrate audited UI, missing/unavailable states and named-tab screenshots; export CSV/JSON/HTML artifacts.
- [ ] Run all unit tests, contract checks, UI smoke and inspect screenshots.
- [ ] Commit feature branch, create PR, attach it and verify Actions against the published SHA.

**Validation commands:** `python -m unittest discover -s tests -q`; `python contract_tests/validate_contracts.py`; `python scripts/run_abf_semantics_validation.py`; `python scripts/abf_research_ui_smoke.py`; `git diff --check`.
