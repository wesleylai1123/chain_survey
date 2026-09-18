# Investment contracts

This repository is the canonical owner of `ResearchSignalV1`.

- A signal is point-in-time data: consumers must align on `available_at`, never on the report period alone.
- `lineage.input_snapshot_id` and `lineage.commit_sha` make every signal reproducible.
- `is_estimate` distinguishes inferred attribution from reported facts.
- Breaking changes require a new versioned directory. Do not import Python modules across repositories.

Validate locally:

```bash
pip install "jsonschema>=4.23,<5"
python contract_tests/validate_contracts.py --report artifacts/contract-compatibility.html
```

`invest_backtest` keeps a consumer snapshot of this schema and consumes JSON artifacts only.
