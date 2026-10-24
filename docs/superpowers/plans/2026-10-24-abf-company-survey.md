# ABF Company Survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver repeatable, sourced and visual company research for three ABF companies before opening the financial-industry route.

**Architecture:** Build one company-research contract from existing audited observations/comparisons, financial context and reviewed primary facts. Render that contract in the existing Tk application and a self-contained portable HTML research report. The semantics audit remains the authority for validation and forecasting eligibility.

**Tech Stack:** Python, pandas, existing Tk/Matplotlib stack, unittest, HTML/SVG, GitHub Actions.

### Task 1: Canonical company research contract

Files: create `core/abf_company_survey.py`, `tests/test_abf_company_survey.py`; reviewed primary facts in `data/abf_company_research_evidence.json`.

- [ ] Write failing tests for three Company × ABF reports; own scenario comparison IDs; chart rows identical to audit samples; future evidence excluded; missing release retained; proxy scope not promoted; financial basis unknown; all four signal fields present.
- [ ] Run `python -m unittest discover -s tests -p test_abf_company_survey.py -v` and confirm failure before implementation.
- [ ] Implement `build_company_survey(audit, factor, facts, *, as_of)` returning contract, generation time, three company records, source/gap status, narratives tied to evidence IDs, trend/scatter series and uncalibrated financial bridge. Use the audited LEVEL observations for trends and full details for per-scenario/per-transform scatter. Do not recalculate or optimize statistical claims in the view.
- [ ] Filter every input by conservative availability and acquisition metadata. Deduplicate exact facts and reject conflicting IDs. Company financial context carries explicit COMPANY_TOTAL scope, UNKNOWN basis unless verified, and nulls for absent values.
- [ ] Re-run focused tests and conduct spec then quality review.

### Task 2: Visual research surface and portable artifact

Files: create `app/abf_company_survey_view.py`, `core/abf_company_survey_html.py`, `scripts/run_abf_company_survey.py`; integrate `app/abf_research_lab.py` and existing snapshot builder.

- [ ] Test HTML escaping, embedded data, all companies/scenarios, missing state and no external chart/network dependency.
- [ ] Render company, scenario, metric and transform controls, trend and scatter plots, sources/four dates, explanation, invalidation conditions and financial bridge from Task 1 contract. Display statistical rejection honestly beside visually suggestive correlation.
- [ ] CLI accepts existing audit/factor/facts/as-of/output-dir and writes `abf_company_survey.json` and `.html`, input hashes and current code revision. Integrate a first company-research tab in the ABF lab without breaking existing tab smoke selectors.
- [ ] Run focused tests and conduct spec then quality review.

### Task 3: Refresh, verification and integration

Files: add `scripts/abf_company_survey_ui_smoke.py`, `.github/workflows/abf-semantics.yml`, documentation, generated artifacts under ignored `artifacts/`.

- [ ] Refresh accessible official evidence and targeted company financial inputs; preserve source acquisition time and report external failures. Add primary-source records only after document verification.
- [ ] UI smoke selects all three companies, independently changes scenarios/transforms, exercises present/unavailable data, and captures app bounds screenshots.
- [ ] Run full unittest suite, contract validation and both old/new UI smoke; inspect actual chart screenshots.
- [ ] Extend deterministic CI with company report/tests/artifacts. Commit on existing feature branch, push PR28, inspect Actions for the exact head and resolve actionable failures without weakening gates.
- [ ] Write acceptance manifest with coverage, tests, screenshots, sources and outstanding external blockers. Report ABF completion status candidly; do not begin financial industry while required ABF checks remain unresolved.
