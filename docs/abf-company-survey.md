# ABF company research

`chain_survey` produces one research record per Company × ABF: 欣興 3037, 景碩 3189, and 南電 8046. The company survey packages the existing semantics audit; a visually strong relationship does not override its OOS, uncertainty, FDR, source or PIT gates.

## What the evidence supports

The reviewed evidence file is `data/abf_company_research_evidence.json`. It contains 39 observations or management statements from official presentations and financial reports, including 11 historical downside/context observations reviewed on 2026-10-26. Each record retains its document, PDF page, URL, measurement period, publication information and actual acquisition time. Acquisition is a historical-replay bound; discovering an old presentation today does not establish that a data pipeline knew its contents in that earlier quarter.

Unimicron's official Q2 2026 presentation separately reports ABF revenue mix: 46% in Q2 2025, 49% in Q1 2026 and 52% in Q2 2026 (PDF page 7). Its disclosed ABF sales growth is 22% QoQ and 51% YoY. These are product disclosures. The company's consolidated gross margin and earnings remain company-wide results. In particular, Q2 net non-operating income of NT$8,925 million is about 57.30% of pretax income of NT$15,576 million (page 4); EPS growth cannot be attributed entirely to ABF operating improvement. The ratio is DERIVED from rounded published inputs.

Kinsus and Nan Ya Q2 reports distinguish three-month from six-month columns. Only the three-month revenue and gross profit are used for the reviewed standalone-quarter margin facts. Kinsus IC-substrate segment revenue and HPC application share include products beyond ABF. Nan Ya's product-development guidance is a disclosed forward-looking statement, not a realized utilization, order or revenue value.

The latest TWSE income-statement OpenAPI/CSV snapshot is YTD. Its Q2 rows match the six-month report columns, not standalone Q2. The feed's output date is not the original filing publication timestamp. It must not replace the verified quarterly columns in this research.

## Research contract and interpretation

`ABFCompanySurveyV1` contains the three companies, primary facts, normalized LEVEL trends, all predeclared scenario/transform choices, audited scatter samples and statistics, company financial context, sources, missing inputs and an uncalibrated Driver→Revenue→GM→EPS bridge. The four signal dates remain explicit; unknown release dates remain null. All current reviewed facts lack exact historical PIT proof, even though their document contents have been verified.

Evidence Status remains DISCLOSED, DERIVED, ESTIMATED, INFERRED or UNKNOWN. Guidance is distinguished with a separate measure/validation field. A company-wide observation is a proxy for ABF and cannot become a product actual. Rounded mix cannot produce exact ABF revenue by multiplication. Correlation does not identify ABF-specific gross margin or an EPS sensitivity.

The financial context retains its FinMind value-provider provenance separately from official primary-document value/basis verification. `data/abf_quarterly_financial_evidence.json` reconciles 12 company-quarters (2025Q1/Q2 and 2026Q1/Q2 for each company) against six inspected consolidated reports. Revenue and gross profit match the provider amounts after the disclosed TWD-thousand conversion. The remaining 66 of 78 company-quarters retain UNKNOWN accounting basis. Published precision determines rounding tolerance; mismatches and future evidence do not verify basis. Original provider values are preserved.

Comparative columns retain the newer document's acquisition bound. An English-report upload date is identified as that document's date, rather than the original Chinese filing time. Neither value agreement nor a filing timestamp proves the historical vintage of the provider's values. `financial_pit_exact` therefore remains false. Current local history covers 26 quarters for each company and 33 monthly company-revenue observations from January 2024 through September 2026; source-specific industry coverage differs and is displayed from actual inputs.

The 2026-10-28 provider refresh contains 79 input rows, including a new Unimicron 2026Q3 row with a conservative 2026-11-29 availability date. That row is omitted before default signal generation; 78 rows enter the current company report. The full-input filing coverage is 78/79 and remains PROXY. CI verifies the actual sourced numerator, denominator and corresponding coverage state; it does not promote the new quarter or assume that all filing timestamps stay complete as fresh inputs arrive.

The Revenue→GM audit predeclares 72 Company × ABF comparisons: two revenue-growth features, two margin-change targets, lags 0/1/2 quarters, three companies and independent UPSIDE/DOWNSIDE scenarios. Each side has a 36-test FDR family, including unavailable tests. Descriptive slopes are ESTIMATED in margin-change percentage points per revenue-growth percentage point. They retain bootstrap intervals, permutation tests, three fixed expanding holdouts, fixed three-company sign agreement, raw sample references and source/date gates. Training observations require both feature and label knowledge before the first test feature. A fold without usable training is not validated OOS evidence. Monthly-revenue features require their own proof and cannot borrow quarterly financial verification. All current comparisons remain rejected for forecasting and all forecast coefficients remain null.

The additional downside history records Unimicron's 2023 quarterly IC-substrate growth/mix and dated Nan Ya inventory/depreciation statements. IC-substrate aggregates remain proxies; qualitative statements have no invented numerical value. These newly acquired documents are lagged historical context, not proven contemporaneous early-warning signals. The 2026-10-28 official Unimicron archive check found no new Q3 document in the inspected presentation or financial-report archives; no Q3 figures were inferred.

## Refresh and acceptance

With persisted industry history restored, refresh the company financial snapshot and build both research outputs:

```powershell
python scripts/refresh_factor_validation.py --stocks 3037,3189,8046 --start 2020-01-01
python scripts/run_abf_research_model.py
python app/main.py --abf-research
```

`python scripts/run_abf_company_survey.py` reuses an existing audit without recalculating correlations. Optional arguments are `--audit`, `--factor`, `--facts`, `--quarterly-financial-evidence`, `--as-of` and `--output-dir`. It writes `artifacts/abf_company_survey.json` and a self-contained `artifacts/abf_company_survey.html`. The HTML needs no network connection for its charts; source links open the original official documents.

Run `python -m unittest discover -s tests -v`, `python contract_tests/validate_contracts.py`, and `python scripts/abf_company_survey_ui_smoke.py`. Linux GUI checks run under Xvfb. Windows screenshots use the target window handle through Pillow 11.2 or later, so a foreground app cannot be mistaken for the research window. The smoke manifest records 24 industry-transform selections, 72 margin selections, exact plotted coordinates/validated OOS subsets and the unavailable state. Both HTML and desktop views consume the same company report; neither refits the selected chart.

Run the existing targeted financial refresh and TPCA/history builders before rebuilding the semantics audit and company survey. PDF facts are explicitly checked against original pages; extracted candidates are never automatically promoted to actuals. The current file records an agent document review, not a claim of human approval. The CLI records input hashes and code revision, and the application and HTML export consume the same company research structure.

The live collector retains the unchanged five-source health checks. When the two MOEA CSV downloads return HTTP 403, it can use the same MOEA monthly USD series distributed by DGBAS, with strict currency/commodity/month checks and explicit original-error/fallback provenance. All 513 overlapping months per commodity matched in the 2026-10-25 equivalence check. See `docs/research-data-pipeline.md` for the source mapping and unpublished-zero guard. Local success does not prove cloud access; acceptance requires the current PR's Actions to pass. Cached snapshots must never be relabeled as successful live collection. System Python 3.14 rejects some government certificate chains under its stricter validation; the bundled Python 3.12 runtime works locally, with certificate verification enabled.

No pure ABF utilization, ASP, order backlog, customer inventory or product gross-margin history is supplied as an actual. Missing product attribution, accounting/PIT proof and company-specific robustness continue to block calibrated ABF forecasts. Financial-industry expansion follows ABF acceptance.
