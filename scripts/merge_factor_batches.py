from __future__ import annotations

import argparse
from pathlib import Path

from core.taiwan_universe import read_and_merge_factor_batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge independently fetched Factor Validation Dataset batches.")
    parser.add_argument("inputs", nargs="+", help="Batch CSV files to merge")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    merged = read_and_merge_factor_batches(args.inputs)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output, index=False)
    print(f"FACTOR_BATCH_MERGE_OK rows={len(merged)} companies={merged['stock_id'].nunique() if not merged.empty else 0}")
    print(f"FACTOR_BATCH_MERGE={output}")


if __name__ == "__main__":
    main()
