# Investment contracts

This repository is the canonical owner of `ResearchSignalV1`.

- A signal is point-in-time data: consumers must align on `available_at`, never on the report period alone.
- `lineage.input_snapshot_id` and `lineage.commit_sha` make every signal reproducible.
- `is_estimate` distinguishes inferred attribution from reported facts.
- Breaking changes require a new versioned directory. Do not import Python modules across repositories.

Validate locally:

```bash
pip install "jsonschema>=4.23,<5" "rfc3339-validator==0.1.4"
python contract_tests/validate_contracts.py --report artifacts/contract-compatibility.html
```

`invest_backtest` keeps a consumer snapshot of this schema and consumes JSON artifacts only.

## Monthly revenue research signal export

Export the latest eligible monthly revenue year-over-year observation for each requested company:

```bash
python scripts/export_research_signals.py \
  --input path/to/mops_abf_monthly_revenue_history.csv \
  --snapshot-acquired-at 2026-10-04T00:00:00+00:00 \
  --as-of 2026-10-04T00:00:00+00:00 \
  --commit-sha 0123456789abcdef0123456789abcdef01234567 \
  --output path/to/research-signals.json
```

The default `--stock-ids` are `3037 3189 8046`; pass another list to override them. The command writes a `ResearchSignalV1` JSON array and a sibling `research-signals.manifest.json`. The manifest contains the original CSV's SHA-256, source URLs, publication methods, skipped-row counts, and quality warnings. Both timestamps must include a timezone, and `--as-of` must be at or after acquisition.

Each signal uses the reported monthly `yoy_pct`, the month's calendar start and end, and `available_at = max(published_at, snapshot_acquired_at)`. A past publication date never makes newly acquired historical data available before acquisition. Rows published after `--as-of`, unreviewed rows, and candidate values are excluded. Every requested company must have an eligible row. Signals are ranked by descending YoY, then entity ID. A regulatory-deadline proxy publication time sets `is_estimate: true`, reduces provenance confidence, and adds `PROXY_PUBLICATION_TIME` to the manifest. Confidence describes source timing and provenance, not predictive accuracy. This export makes no forecast or efficacy claim.

`source_url` must be an HTTP(S) URL with a host. `knowledge_time_method` must be `regulatory_deadline_proxy`, `source_reported`, or `actual_publication_time`; unknown methods are rejected instead of being assigned direct-publication confidence.

Output paths are checked before writing. If replacing the manifest fails, the
exporter restores the prior signal file or removes a newly created signal file,
so a failed export does not leave a successful partial pair.

Timestamp inputs require RFC3339 syntax and a valid hour/minute timezone offset.
Signal availability is serialized in UTC. Include the RFC3339 validation
dependency above when checking schema date-time formats.
