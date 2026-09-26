# ABF source observations

The two CSV files in `data/` are intentionally header-only. A field name or a
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
period end, numeric value and unit, timezone-aware publication time, direct
source URL, and a short identifying excerpt. Keep revisions as separate source
records only when they do not duplicate the same metric, company, period and
source. An observation becomes `INSUFFICIENT_HISTORY`; it is not promoted to
`AVAILABLE` or used to calibrate a sensitivity until a separate historical
validation establishes enough point-in-time samples and cross-company support.

The repository contains the official MOPS upload timestamps for all 78 company
quarters from 2020 Q1 through 2026 Q2 for 3037, 3189 and 8046. Product and
downside historical observations remain open for source collection.
