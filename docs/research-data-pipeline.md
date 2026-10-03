# Research Data Pipeline

## Goal

Every research-data run must be reproducible and auditable:

1. rediscover or refetch the configured public sources,
2. store raw bytes only when the content SHA-256 changes,
3. process the fetched content with versioned repository code,
4. validate point-in-time and semantic contracts,
5. emit a run manifest containing input/output hashes and validation results,
6. persist validated raw snapshots and audit manifests to the `evidence-data` branch.

A successful download alone is never treated as validated research data.

## Entry points

### Unified scheduled/manual run

`.github/workflows/research-data-pipeline.yml`

This is the only daily scheduler. It invokes:

- Live Free Evidence Connectors
- ABF Source Health
- Free Evidence History

The child workflows remain independently callable on pull requests and manual dispatch. Production push/schedule execution goes through the unified orchestrator so evidence-data writers run in a controlled sequence.

## Persistence model

`main` contains code, schemas, tests, source registries and workflows.

`evidence-data` contains durable collected data:

- `persistent/free_evidence/raw/<source_id>/...`
- `persistent/abf_documents/<stock_id>/<sha256>.pdf`
- `data/history/...`
- `persistent/run_manifests/live/...`
- `persistent/run_manifests/abf/...`
- `persistent/run_manifests/history/...`

GitHub Actions artifacts are previews/debug outputs only. They are not the long-term audit store.

## Idempotence

Raw data is content-addressed by SHA-256.

If the same source content is fetched again:

- no duplicate raw snapshot is written,
- the original first-seen collection time remains the canonical point-in-time availability,
- a new run manifest is still emitted so the repeated check is auditable.

If the SHA changes, a new raw snapshot and new canonical availability time are created.

## Validation status

- `PASS`: every required gate passed.
- `DEGRADED`: mandatory gates passed, but a non-critical quality threshold failed.
- `FAIL`: at least one mandatory gate failed. The workflow exits non-zero before persistence.

Examples of mandatory gates:

- required source coverage,
- non-empty processed output,
- no future leakage,
- raw SHA lineage,
- pipeline run lineage,
- candidates remain `CANDIDATE` until reviewed,
- reliability values remain explicitly labelled priors.

## Traceability

Processed live evidence includes:

- `raw_sha256`
- `raw_snapshot_path`
- `pipeline_run_id`
- `availability_policy`
- `reliability_basis`
- `exposure_basis` when applicable

ABF operating candidates include:

- source URL and source page,
- document SHA-256,
- persisted raw document path,
- pipeline run ID,
- extraction rule,
- source permission / ABF context gate,
- review status.

Each run manifest also records:

- Git commit SHA,
- run attempt,
- input hashes,
- output hashes,
- validation checks and final status.

## Concurrency

All workflows that can write to `evidence-data` use the shared concurrency group:

`evidence-data-writer`

This prevents live, ABF and history jobs from racing or overwriting each other's commits.

History persistence uses a separate checkout of `evidence-data`; it must never use `git switch -C evidence-data` or force-push the data branch.

## Verification workflow

For any suspicious metric:

1. find the processed row and its `pipeline_run_id`,
2. open the matching persisted run manifest,
3. locate `raw_snapshot_path` and confirm the SHA,
4. inspect the raw source,
5. confirm the processing rule/code revision in the manifest,
6. inspect the validation result,
7. only then use the observation for correlation/sensitivity calibration.

This is the required audit path for production research data.


## Cross-run continuity

After the first production bootstrap, every subsequent run compares current processed data with the last-known-good baseline stored under:

- `persistent/baselines/live/`
- `persistent/baselines/abf/`
- `persistent/baselines/history/`

Destructive regressions such as history-key deletion, latest-period regression, or severe row-count collapse fail closed. Non-destructive warnings such as source disappearance or candidate shrinkage are reported as `DEGRADED`.

## Unified health report

The orchestrator summary job reads the three permanent run records for the same pipeline run ID and produces:

- `research_data_pipeline_summary.json`
- `research_data_pipeline_summary.csv`

The JSON contains the full validation / continuity payloads for live, ABF and history. The CSV provides a compact status table with manifest status, validation status, continuity status, failed/degraded check counts and code revision.

Successful production summaries are also persisted to:

`persistent/run_manifests/summary/<run_id>.{json,csv}`

A production research-data run is considered complete only when all three child workflows succeed and the unified health report is not `FAIL`.
