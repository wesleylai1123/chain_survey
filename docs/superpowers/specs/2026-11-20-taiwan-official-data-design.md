# Taiwan ETF and USD/TWD official data integration

## Scope and verified sources

Continue the approved multi-asset architecture on the existing feature PRs. Do not merge either PR or change ABF calculations. Start with the two explicit example instruments 0050 (passive) and 00981A (active), plus USD/TWD spot; these are comparison examples, not recommendations.

Verified official interfaces:
- TWSE monthly `exchangeReport/STOCK_DAY`: unadjusted daily closing observations, security ID and requested calendar month.
- TWSE `/rwd/zh/ETF/etfDiv`: distribution amount, ex date, record date and pay date. Its distribution policy prose does not establish the actual income/ROC composition.
- TWSE `/rwd/zh/split/TWTCAU`: split/reverse-split reference prices and dates, but reference-price division is rounded and does not establish an exact unit ratio. Preserve these records as evidence; do not infer an exact split factor.
- CBC `/api/OpenData/FTDOpenData_Day`: USD/TWD interbank closing spot history, quoted TWD units per USD. This is a research reference, not a broker executable rate.

## Approaches

1. Recommended: capture immutable official responses, offer a raw-data view, and add a narrow versioned `unadjusted_price` basis that explicitly blocks total-return/cash investment claims. Verified normalized total-return inputs continue using the existing V1 flow. This enables usable real-data inspection without guessing adjustment or tax facts.
2. Treat raw closes as adjusted prices after observing no split rows: fewer changes but cannot certify complete corporate-action coverage; reject this approach.
3. Wait for a full licensed adjusted-data provider: appropriate for production portfolio accounting later, but delays all current official-data inspection and requires new provider access.

## Ingestion and availability

The main product owns source adapters and capture/replay CLIs. The numerical service owns calculation behavior and versioned result schemas. Continue JSON-only cross-repository boundaries.

Every HTTP fetch records the exact URL, HTTP status, response acquisition-completion time in UTC, content bytes, SHA256 and parser version. Raw data is stored content-addressed and never overwritten. A capture manifest freezes the requested instruments/window, response identities, metadata sources, parsed rows, coverage and limitations. Offline replay uses the original recorded acquisition times and verifies every raw hash; replay must not fetch or re-date history.

Original publication times are not supplied by these history endpoints. A conservative observation-time upper bound may be used as published_at=acquired_at only with explicit `OBSERVED_AT_ACQUISITION_NOT_ORIGINAL_PUBLICATION` lineage and visible UI text. Such a download is an as-acquired historical snapshot and does not certify historical-vintage backtesting. Future economic rows are rejected, unknown prices remain null and missing dates are retained on the union of supplied exchange sessions; no interpolation, price/FX forward fill, or invented exchange calendar.

Requests are bounded by validated dates, supported instruments and monthly request count, with timeouts, bounded retry and pacing. Source schema drift, wrong security/month, conflicting duplicates, malformed dates, nonfinite numbers, wrong currency direction or HTTP failures fail the collection rather than mark it successful. A failed run may retain raw diagnostic evidence but must not replace the latest-good manifest/request.

## Versioned boundary

Preserve all 1.0.0 schemas and fixtures. Add request/result version 1.1.0 schemas in separate directories, accepting `unadjusted_price` in instrument return_basis. Engine validates the selected version and returns the matching version. Raw-price instruments retain quoted observations and distributions but return null for total return, rolling total returns, investment cash and benchmark comparison metrics, with explicit adjustment/completeness reasons. They must not accidentally use the total-return-index branch. Normalized 1.0.0 results remain byte-compatible.

The actual USD/TWD spot instrument may use the existing FX path, explicitly excluding carry/leverage. Default risk-free, withholding and all transaction-fee assumptions are null; explicit user zero is never inferred from missing input. Distribution classification stays unknown. No fee, benchmark, holding or income composition is guessed.

## Main-product UI

Add a source acquisition dialog with date range, explicit supported symbols, and reporting currency. Collection runs off the Tk event thread and does not accept stale worker output after settings change. Add an Official Data tab showing date/security/raw close, announced distributions, exact FX, source URLs and coverage. A price plot is labeled unadjusted and not compounded/reinvested wealth. Allow saving/loading a frozen capture or request and reproduce offline without access credentials.

An explicit comparison-data control keeps the existing sourced-normalized research path available. Loading real official data must remove TEST ONLY labels and instead show the capture timestamp and the limitations of as-acquired/unadjusted data. Empty/failure/missing states remain visible. No finance metrics are fabricated to make the page look populated.

## Verification and delivery

Tests first: actual response fixtures, ROC/Gregorian dates, missing prices, identity/month mismatch, payload drift, duplicates, timezones, hash tampering, offline deterministic replay, collection rollback, raw-price safety, old V1 compatibility, FX direction, UI nonblocking/stale workers and visible source limitations. Real official response samples remain explicitly sourced fixtures, never synthetic market facts. Capture a live bounded window for actual UI validation, retaining its original bytes and timestamps locally.

Run both complete suites and old/additive contract checks, inspect real populated/missing/failure UI screenshots, independently review, push existing feature PRs and wait for current-head automatic CI. Keep live collection opt-in/manual; public pull-request CI must use frozen official fixtures with no market-network dependency. Update the delivery report with source coverage, unsupported claims and remaining licensed/issuer-source needs.
