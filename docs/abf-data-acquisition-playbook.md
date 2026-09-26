# ABF primary-source acquisition playbook

The ABF model uses a two-stage ingestion design:

1. **discover stable primary documents** from regulator/company archive pages;
2. **extract observations** from the discovered documents.

Do not bind a metric parser to one hard-coded PDF URL. Archive pages and regulator
APIs are the stable contract; individual PDF URLs are discovered artifacts.

## Source hierarchy

1. TWSE OpenAPI / MOPS regulatory data.
2. TWSE/MOPS document and investor-event archives.
3. Company investor-conference / financial-report archives.
4. Company annual, sustainability and technology-roadmap pages.
5. Secondary research is discovery-only and must never enter calibration tables.

The machine-readable source contract is `data/abf_source_registry.csv`.

## Stability contract

Every registry source declares:

- `source_id` — stable internal key;
- `parser_type` — parser family, not a one-off script;
- `refresh_cadence`;
- `health_selector` — expected content proving the endpoint still has the intended role;
- `fallback_source_id` — another primary source used when the endpoint fails;
- `use_for` — metrics/events the source is allowed to support.

`scripts/collect_abf_source_manifest.py` performs retries, source health checks,
link discovery, SHA-256 lineage and fallback. It writes:

- `artifacts/abf_source_manifest.csv`: discovered PDF/video/document URLs;
- `artifacts/abf_source_health.csv`: endpoint health and content hashes.

A company website redesign therefore breaks only that parser/source; regulator
fallbacks remain available and the failure is visible in the health artifact.

## Current stable entry points

### 3037 Unimicron

- TWSE structured monthly-revenue API.
- TWSE/MOPS document archive for filings and investor material.
- MOPS company disclosure page.
- TWSE WebPro as a management-commentary/video fallback.

### 3189 Kinsus

- TWSE structured monthly-revenue API.
- Official investor-conference archive.
- Official sustainability-report archive for production/capacity proxies.
- Official monthly-revenue page.
- MOPS fallback.

### 8046 Nan Ya PCB

- TWSE structured monthly-revenue API.
- Official investor/financial archive, which exposes monthly sales, quarterly
  statements, investor-event downloads and videos.
- Official ABF technology roadmap.
- MOPS and TWSE WebPro fallbacks.

## Observation extraction targets

### Utilization
Search for utilization / loading / 稼動率 / 滿載 / full utilization. Preserve
exact values, ranges and qualitative values separately. Never turn “full” into
an invented 100%.

### Product mix
Prefer explicit ABF/BT mix. IC-substrate mix remains a named proxy and cannot
satisfy exact ABF product-mix coverage.

### Capacity
Store line start, expansion, qualification, ramp and full-utilization statements
as dated supply events even when physical capacity is not disclosed.

### Guidance / downside
Capture point-in-time management statements: order visibility, pricing pressure,
inventory correction, customer delay, order cuts, yield issues, depreciation
pressure and utilization decline.

## Acceptance rule

An observation is calibration-eligible only when it records stock/company,
period/event date, scope, actual source-provided value or qualitative state,
publication knowledge time, direct primary URL, page/timestamp and excerpt.
Source discovery and observation extraction are separate stages so a discovered
document never becomes a model input merely because it exists.
