# ABF company research completion

The user approved completing ABF before moving to financial companies. `chain_survey` remains the only research product. The existing ABF semantics audit is the statistical authority; this change turns its evidence into a usable company research surface for 欣興 (3037), 景碩 (3189), and 南電 (8046).

## Research output

Each Company × ABF report contains a concise evidence-based assessment, operating mechanism, monthly industry/company trend, predeclared transform/scenario correlation chart, financial context, sources, missing data and explicit conditions that would invalidate an interpretation. Company-total revenue/financials and PCB industry data retain their proxy scopes. No eligible ABF relationship means no calibrated product forecast.

The report uses one machine-readable `ABFCompanySurveyV1` structure for the Tk research tab and a portable self-contained HTML export. Charts use only audited sample rows and normalized observations, retain dates and provenance, distinguish full sample from chronological OOS, and never select a winning transform on the holdout. Correlation alone does not establish a forecasting model. Upside/downside are independently selectable and retain their own audit evidence. Every chart identifies units, transformations, timing, sample count, source scope and PIT limitations.

## Evidence and financial context

Canonical Evidence Status values remain DISCLOSED, DERIVED, ESTIMATED, INFERRED and UNKNOWN. Missing or unavailable values are null. Company financial series are context at company scope; quarterly accounting basis is UNKNOWN unless independently verified. Revenue→GM remains uncalibrated where basis, PIT, product attribution or company-specific robustness is missing. The four signal dates remain explicit; real generation time and historical replay cutoff are separate. Later-acquired disclosures cannot silently become historically known facts.

Primary qualitative/quantitative facts use a reviewed local evidence file with source URL, document/page, observation/release/availability/acquisition times and scope. The system rejects untraceable, future and conflicting facts. Source availability and missing inputs remain visible; a failed external endpoint is not replaced with an invented value or a lowered health gate.

## Acceptance

The user can select each of three companies and see sourced facts, audited trend/scatter evidence, independent upside/downside status, OOS/uncertainty/FDR details, financial bridge and priority research gaps. Empty inputs render an unavailable state. CLI produces JSON and self-contained HTML from the same contract. Unit regressions cover PIT/proxy/missing states and chart correspondence. UI smoke exercises companies/scenarios and captures screenshots. Existing tests and contracts pass. PR Actions must be green before calling the integration complete; confirmed external failures remain an explicit blocker. Financial industry work begins only after ABF acceptance.
