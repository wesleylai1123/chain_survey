# ABF source observations

The two CSV files in `data/` are source-intake files. A field name or a
structural model equation is not evidence that a historical observation exists.

## Quarterly filing time

Add a row to `data/abf_filing_observations.csv` only after verifying the exact
publication timestamp of the **quarterly financial report** against a direct
official TWSE/MOPS page. Columns are `stock_id`, `report_date` (quarter end),
`published_at` (ISO 8601 including timezone), `source_url`, `document_name`, and `document_type`
(`quarterly_financial_report`). A board meeting, preliminary result, filing
deadline, or financial period end does not qualify as this timestamp. Duplicate
company-quarter rows fail closed for review.

The factor panel keeps the original timestamp and URL. For daily price studies,
its `available_date` is the calendar day after publication; the target builder
then takes the next available trading day. Quarters without a verified record
keep the +60/+90 day proxy and the coverage audit remains `PROXY` until every
ABF company-quarter in the panel is source-backed.

## Product and downside observations

Use `data/abf_operating_observations.csv` for a measured ABF product metric or
documented downside event. Each row requires the requirement `data_id`, stock,
period end and scope, numeric value and unit, publication precision, direct
source URL, source page, and a short identifying excerpt. Use `EXACT_SECOND`
only with a timezone-aware `published_at`. When the original document supplies
only its date, use `DATE_ONLY` with `published_date`; availability is then set
conservatively to the following day.

Calibration data is stricter than general research evidence. The operating
intake accepts only primary company/regulator hosts (TWSE/MOPS or the official
sites for Unimicron, Kinsus and Nanya PCB). Analyst reports, media summaries and
other secondary sources may be useful for research discovery, but they must not
enter the source-backed calibration table. The verifier derives `source_host`
and `source_tier=PRIMARY` and rejects an unapproved host instead of silently
promoting it.

Keep revisions as separate source records only when they do not duplicate the
same metric, company, period, scope and source. A source-backed row becomes
`INSUFFICIENT_HISTORY`; it is not promoted to `AVAILABLE` or used to calibrate
a sensitivity until separate historical validation establishes enough
point-in-time samples and cross-company support. Coverage detail reports the
primary-source observation count, company count, historical span and declared
minimum sample gates so a partial series cannot look complete.

The repository contains the official MOPS upload timestamps for all 78 company
quarters from 2020 Q1 through 2026 Q2 for 3037, 3189 and 8046.

## Product-layer proxy series

The official Unimicron Q4 2025 operating presentation dated 2026-02-25 supplies
four technology-mix observations for IC substrate: 2024 annual 61%, 2025Q3 57%,
2025Q4 59%, and 2025 annual 58%. Pages 8 and 10 are recorded with each row. The
document provides a publication date but no clock time, so the observations use
`DATE_ONLY` precision and become available on the following day.

IC substrate combines ABF and BT. These observations therefore remain an
`INSUFFICIENT_HISTORY` supporting proxy and do not satisfy the core
`abf_product_mix_history` requirement. Exact ABF mix, ASP, volume, utilization,
capacity and downside-event histories remain open for original-source collection.
