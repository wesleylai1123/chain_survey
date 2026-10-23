# ABF semantics validation

`chain_survey` owns this research product. ABF is the reference slice; every result is keyed by company and product. The three companies' consolidated revenue is a proxy for ABF product revenue. No product actual, calibrated margin beta or EPS attribution is implied.

The metric registry is `data/abf_metric_semantics.json`; `contracts/metric-semantics/v1/schema.json` validates research observations. Evidence status is DISCLOSED, DERIVED, ESTIMATED, INFERRED or UNKNOWN. Statistical validation and model eligibility are separate fields.

- LEVEL means identity of the recorded measure. A recorded YoY rate is still a change measure, expressed in percent.
- CHANGE means the difference between adjacent calendar months' recorded YoY rates, expressed in percentage points. Gaps are excluded. Availability and publication depend on both inputs.
- Accounting basis is explicit. YTD cash flow, standalone-quarter cash flow, margins with unverified accounting basis and price returns cannot be interchanged. The financial return targets use price returns, excluding dividends; they are not total returns.
- Each observation carries `observation_date`, `release_date`, `available_at` and `signal_generated_at`. Unknown release/availability values stay null. Proxy publication dates cannot establish exact PIT. Current snapshots do not prove historical data-vintage availability.
- ResearchSignalV1 remains a frozen transfer boundary. Its entity-keyed manifest companion now carries the four times and company/product/scope semantics. `signal_generated_at` in this replay interface is the explicit as-of evaluation time, not a claim about an earlier physical execution.

Run `python scripts/run_abf_semantics_validation.py --as-of 2026-10-23T00:00:00Z`. Inputs default to persisted `evidence-data` history and optional local factor data. No input produces explicit unavailable rows. The report records input, registry and schema hashes, code revision, generation time, configuration, exact used rows and dependency IDs.

The 120 predeclared comparisons cover five source metrics, three companies, two independent scenarios and all four feature/target transform pairs. The lag is fixed at one month. No transform is selected using holdout performance. Forecast features must be available before the target economic period ends. Three chronological OOS folds purge training labels unknown at the first test feature time. Conditional bootstrap/permutation blocks stop at calendar gaps. FDR uses all 60 planned comparisons separately for each scenario, assigning missing tests p=1. Missing companies count against agreement in the fixed three-company denominator.

`eligible` requires all statistical gates plus complete provenance, exact PIT and nonproxy product scope. Statistically passing proxy results are `support-only`; other results are `reject`. Reject is a model-use decision, not a claim that an economic mechanism cannot exist. Short conditional history is a material limitation.

Revenue → GM now aligns calendar quarters, excludes missing availability, uses a common date holdout and retains company-specific descriptive results. Pooled robustness is identified as a pooled reference and never grants a company's own validation. Unverified/YTD/TTM basis blocks calibration. The handoff retains null betas where evidence is insufficient and prioritizes downside source history and Revenue → GM before GM → EPS.

Artifacts in `artifacts/`:

- `abf_semantics_validation.json` / `.html`: full evidence and review report.
- `abf_transform_comparison.csv`: flat Company × Product comparison table.
- `abf_calibration_handoff.json`: company-specific calibration prerequisites.
- `abf_downside_source_priorities.json`: connected proxy history and explicitly missing product sources.
- `abf-semantics-present.png` / `abf-semantics-unavailable.png`: exercised UI states.

`ABF Semantics Contract` publishes the report and screenshots in Actions. `ABF Research Model` embeds the same audit in snapshot V2; its legacy basket fits are exploratory and cannot grant product forecast permission.
