from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.taiwan_universe import read_and_merge_factor_batches


def run_batch(args, batch_index: int, output: Path) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "refresh_factor_validation.py"),
        "--start", args.start,
        "--end", args.end,
        "--stocks", "",
        "--universe-file", args.universe_file,
        "--batch-size", str(args.batch_size),
        "--batch-index", str(batch_index),
        "--sleep-seconds", str(args.sleep_seconds),
        "--cache-dir", args.cache_dir,
        "--manifest", args.manifest,
        "--output", str(output),
        "--raw-dir", str(Path(args.raw_root) / f"batch_{batch_index:03d}"),
    ]
    if args.token:
        cmd += ["--token", args.token]
    if args.retry_failed_only:
        cmd.append("--retry-failed-only")
    print("RUN_BATCH", batch_index, " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Taiwan full-universe factor collection in resumable cached batches.")
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--max-batches", type=int, default=None, help="Limit batches for CI/smoke runs; omit for all remaining batches.")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--token", default=None)
    parser.add_argument("--retry-failed-only", action="store_true")
    parser.add_argument("--cache-dir", default=str(ROOT / "artifacts" / "factor_cache"))
    parser.add_argument("--manifest", default=str(ROOT / "artifacts" / "factor_cache_manifest.json"))
    parser.add_argument("--batch-dir", default=str(ROOT / "artifacts" / "factor_batches"))
    parser.add_argument("--raw-root", default=str(ROOT / "artifacts" / "factor_batch_raw"))
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "factor_validation_full.csv"))
    args = parser.parse_args()

    universe = pd.read_csv(args.universe_file)
    total = len(universe)
    total_batches = (total + args.batch_size - 1) // args.batch_size
    stop = total_batches if args.max_batches is None else min(total_batches, args.start_batch + args.max_batches)
    batch_dir = Path(args.batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    completed: list[Path] = []
    for batch_index in range(args.start_batch, stop):
        output = batch_dir / f"factor_batch_{batch_index:03d}.csv"
        run_batch(args, batch_index, output)
        completed.append(output)

    all_batch_files = sorted(batch_dir.glob("factor_batch_*.csv"))
    if not all_batch_files:
        raise RuntimeError("No factor batch output files were produced")
    merged = read_and_merge_factor_batches(all_batch_files)
    final_output = Path(args.output)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(final_output, index=False)
    print(f"FULL_UNIVERSE_RUN_OK selected_batches={args.start_batch}:{stop} total_batches={total_batches} cached_batch_files={len(all_batch_files)} rows={len(merged)} companies={merged['stock_id'].nunique() if not merged.empty else 0}")
    print(f"FULL_UNIVERSE_DATASET={final_output}")


if __name__ == "__main__":
    main()
