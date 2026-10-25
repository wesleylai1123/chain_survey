# ABF company research

`chain_survey` produces one research record per Company × ABF: 欣興 3037, 景碩 3189, and 南電 8046. The company survey packages the existing semantics audit; a visually strong relationship does not override its OOS, uncertainty, FDR, source or PIT gates.

## What the evidence supports

The reviewed evidence file is `data/abf_company_research_evidence.json`. It currently contains 28 observations or management statements from official presentations and financial reports, reviewed on 2026-10-24. Each record retains its document, PDF page, URL, measurement period, publication information and actual acquisition time. Acquisition is a historical-replay bound; discovering an old presentation today does not establish that a data pipeline knew its contents in that earlier quarter.

Unimicron's official Q2 2026 presentation separately reports ABF revenue mix: 46% in Q2 2025, 49% in Q1 2026 and 52% in Q2 2026 (PDF page 7). Its disclosed ABF sales growth is 22% QoQ and 51% YoY. These are product disclosures. The company's consolidated gross margin and earnings remain company-wide results. In particular, Q2 net non-operating income of NT$8,925 million is about 57.30% of pretax income of NT$15,576 million (page 4); EPS growth cannot be attributed entirely to ABF operating improvement. The ratio is DERIVED from rounded published inputs.

Kinsus and Nan Ya Q2 reports distinguish three-month from six-month columns. Only the three-month revenue and gross profit are used for the reviewed standalone-quarter margin facts. Kinsus IC-substrate segment revenue and HPC application share include products beyond ABF. Nan Ya's product-development guidance is a disclosed forward-looking statement, not a realized utilization, order or revenue value.

The latest TWSE income-statement OpenAPI/CSV snapshot is YTD. Its Q2 rows match the six-month report columns, not standalone Q2. The feed's output date is not the original filing publication timestamp. It must not replace the verified quarterly columns in this research.

## Research contract and interpretation

`ABFCompanySurveyV1` contains the three companies, primary facts, normalized LEVEL trends, all predeclared scenario/transform choices, audited scatter samples and statistics, company financial context, sources, missing inputs and an uncalibrated Driver→Revenue→GM→EPS bridge. The four signal dates remain explicit; unknown release dates remain null. All current reviewed facts lack exact historical PIT proof, even though their document contents have been verified.

Evidence Status remains DISCLOSED, DERIVED, ESTIMATED, INFERRED or UNKNOWN. Guidance is distinguished with a separate measure/validation field. A company-wide observation is a proxy for ABF and cannot become a product actual. Rounded mix cannot produce exact ABF revenue by multiplication. Correlation does not identify ABF-specific gross margin or an EPS sensitivity.

The financial context retains its FinMind value-provider provenance separately from the official filing URL used to verify publication time. Unverified accounting basis stays UNKNOWN. Current local history covers 26 quarters for each company and 33 monthly company-revenue observations from January 2024 through September 2026; source-specific industry coverage differs and is displayed from actual inputs.

## Refresh and acceptance

With persisted industry history restored, refresh the company financial snapshot and build both research outputs:

```powershell
python scripts/refresh_factor_validation.py --stocks 3037,3189,8046 --start 2020-01-01
python scripts/run_abf_research_model.py
python app/main.py --abf-research
```

`python scripts/run_abf_company_survey.py` reuses an existing audit without recalculating it. Optional arguments are `--audit`, `--factor`, `--facts`, `--as-of` and `--output-dir`. It writes `artifacts/abf_company_survey.json` and a self-contained `artifacts/abf_company_survey.html`. The HTML needs no network connection for its charts; source links open the original official documents.

Run `python -m unittest discover -s tests -v`, `python contract_tests/validate_contracts.py`, and `python scripts/abf_company_survey_ui_smoke.py`. Linux GUI checks run under Xvfb. Windows screenshots use the target window handle through Pillow 11.2 or later, so a foreground app cannot be mistaken for the research window. The smoke manifest records 24 selections, exact plotted coordinates/OOS subsets and the unavailable state.

Run the existing targeted financial refresh and TPCA/history builders before rebuilding the semantics audit and company survey. PDF facts are explicitly checked against original pages; extracted candidates are never automatically promoted to actuals. The current file records an agent document review, not a claim of human approval. The CLI records input hashes and code revision, and the application and HTML export consume the same company research structure.

The live collector retains the unchanged five-source health checks. When the two MOEA CSV downloads return HTTP 403, it can use the same MOEA monthly USD series distributed by DGBAS, with strict currency/commodity/month checks and explicit original-error/fallback provenance. All 513 overlapping months per commodity matched in the 2026-10-25 equivalence check. See `docs/research-data-pipeline.md` for the source mapping and unpublished-zero guard. Local success does not prove cloud access; acceptance requires the current PR's Actions to pass. Cached snapshots must never be relabeled as successful live collection. System Python 3.14 rejects some government certificate chains under its stricter validation; the bundled Python 3.12 runtime works locally, with certificate verification enabled.

No pure ABF utilization, ASP, order backlog, customer inventory or product gross-margin history is supplied as an actual. Missing product attribution, accounting/PIT proof and company-specific robustness continue to block calibrated ABF forecasts. Financial-industry expansion follows ABF acceptance.
