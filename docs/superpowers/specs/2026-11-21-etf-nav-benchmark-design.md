# ETF NAV and official return index context

## Scope and current state

Continue the existing feature PRs without merging. The approved raw-price capture, request/result 1.1.0, numerical service and ABF paths remain in place. Add same-date NAV valuation facts and two independent total-return reference indices. This is a source/context extension, not permission to treat raw ETF closes as total-return inputs.

The current heads are chain_survey `2421a34a28fbf4b0790ccf01668d760ba41fb5e3` and invest_backtest `5e0121bbb2d1d18a867dea0fa283be8f486ac1fd`. Both PRs remain open. The code graph does not yet contain the new multi_asset modules; inspection therefore uses the known source files after a graph search returned no matches.

## Verified source interfaces

- [Government dataset 11109](https://data.gov.tw/dataset/11109), under the Government Open Data License, links to `https://www.sitca.org.tw/MemberK0000/F/03/nav.csv`. A verified 2026-11-21 acquisition returned UTF-8 CSV with 12 named columns, including date, NAV, currency and beneficiary-certificate code. The response contains 0050 and 00981A NAV observations dated 2026-11-20. Identity must use the certificate code, preserving the leading zero; internal fund codes and name matching are insufficient.
- The [TWSE OpenAPI catalogue](https://openapi.twse.com.tw/v1/swagger.json) documents `https://openapi.twse.com.tw/v1/indicesReport/TAI50I` with separate `Taiwan50Index` and `Taiwan50TotalReturnIndex` fields. The acquired response contains 15 dates from 2026-11-02 through 2026-11-20.
- The same catalogue documents `https://openapi.twse.com.tw/v1/indicesReport/MFI94U`, with `TAIEXTotalReturnIndex`. Its acquired response covers the same 15 dates.

The URLs have no historical range parameter in this contract. Each download is a snapshot of the dates actually supplied. Future acquisitions may expose different dates; never manufacture a longer history. Original publication times remain unknown and availability stays conservatively bounded by acquisition.

Source-audit originals and exact URL/time/hash metadata are retained locally under `artifacts/source-audit-2026-11-21/`.

## Approaches

1. Recommended: add optional NAV and reference-index sources to the existing immutable capture, retain the exact as-acquired evidence, and expose only calculations supported by matching dates. The existing numerical service can consume total-return indices without modification.
2. Reconstruct ETF adjusted returns now from individual split/distribution announcements. One exact 0050 split ratio is verifiable, but it cannot certify complete corporate-action and distribution histories. Defer this until the coverage evidence is adequate.
3. Add a licensed adjusted-history provider. This can address longer histories later, but requires a selected provider and access not present in this workspace.

## Capture and compatibility

Add an explicit `include_etf_context` option. The CLI defaults to the previous source set unless `--include-etf-context` is supplied. The acquisition dialog offers a clearly named NAV/reference-index checkbox, selected by default for the new workflow.

Keep old capture version 1.0.0/parser `taiwan-official-1.0.1` replay semantics intact. Context captures use manifest version 1.1.0 and a separately allowlisted parser version. Expected source identities/order/URLs depend on the manifest version; an old snapshot never gains new sources or current metadata during replay. Request/result schema version stays 1.1.0; no existing contract bytes change.

Freeze source definitions and benchmark identities with the new capture. The three extra exact bodies and every failed attempt use the existing bounded HTTPS/hash/atomic-write audit path. Any required context source failure fails that opted-in capture and preserves latest-good. The user can explicitly collect the prior source set; there is no silent partial success or cached substitution.

## Parsing and context

Use strict UTF-8 CSV with the exact required header set, finite positive NAV values or explicit missing markers, exact certificate code, valid calendar dates, TWD and conflict detection. Retain only supported ETF identities for application data; unrelated funds do not become instruments. Validate source hash/size/status and acquisition times through the existing capture boundary.

Index responses require their documented JSON fields and finite positive levels or explicit missing values. Parse the seven-digit ROC compact dates explicitly in the new index parser. Keep the price-index field as source context; use only the documented total-return field in a `total_return_index` instrument. Do not add ETF dividends to either index. Duplicate conflicting rows, schema drift and future economic dates fail closed.

The primary research grid remains the supplied ETF-date union. Index observations outside that requested grid do not enter the numerical service. Missing index dates remain absent and visible in coverage; a current-month series does not become a complete three-month benchmark. NAV observations retain their actual date even when outside the chosen research window and are labeled accordingly.

Two reference instruments, `TWSE.TAI50.TR` and `TWSE.TAIEX.TR`, are independent research references in the opted-in request. Do not automatically populate ETF `benchmark_id` or claim these are the exact contractual fund performance benchmarks. Frozen context records explain their source and purpose. Existing tracking/alpha calculations remain unavailable for unadjusted ETF inputs.

## NAV valuation and UI

Add a separate append-only-position tab named 「淨值與基準」, preserving existing tab indices. Display each ETF's actual NAV date/value/currency, matching source close and `close / NAV - 1`, plus provenance and a clear availability reason.

A premium/discount is available only for an in-window exact-date close and NAV with matching native currency, positive values and both records available at the chosen cutoff. Never pair today's NAV with yesterday's close, convert missing currency data, use a nearby date, or infer a traded spread. Label it an end-of-day valuation ratio, not an executable quotation or total return.

Display each reference index's supplied date range, usable rows versus research-grid dates, source and total-return basis. Existing comparison/rolling/correlation views may render those valid index series through the unchanged service. The raw ETF rows keep adjustment restrictions. A short-window capture can have complete index coverage; a longer capture shows gaps explicitly.

Setting changes, source failures and stale workers follow the existing rules and preserve loaded official facts. Old snapshots show an explanatory no-context state in the new tab, not fabricated NAV or empty success.

## Verification and delivery

Tests first: actual sourced CSV/JSON fixtures, leading-zero identity, wrong currency/date, missing/zero/nonfinite values, ROC compact dates, duplicate/header drift, price-versus-total-return field selection, future cutoffs, unequal date/currency pairs, and current-month coverage gaps.

Verify deterministic replay for both capture versions, exact old request bytes, source/metadata/hash tampering rejection and latest-good protection. Validate actual numerical-service integration with five instruments, unchanged ETF return restrictions, and index returns independently recomputed from source levels.

Capture a bounded 2026-11-02 to 2026-11-20 real sample, freeze originals with source times, and inspect populated, missing-date, out-of-window NAV and old-snapshot UI artifacts. Public CI uses frozen evidence without live providers. Run main/ABF, numerical-service and contract checks; update the existing PRs and wait for every current-head automatic check. No merge or deployment.

## Remaining gates

ETF total return, realized portfolio cash, fee-aware income and exact tracking/alpha still require verified adjusted histories, full event coverage and the relevant assumptions. Tax classification is not a prerequisite for mathematical total return, but actual payout composition and account-specific rules remain necessary for relevant income/tax interpretations. This extension does not relax those requirements or certify historical-vintage availability.
