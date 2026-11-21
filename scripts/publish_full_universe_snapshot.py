from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def batch_index_from_name(path: Path) -> int:
    return int(path.stem.rsplit("_", 1)[-1])


def build_collection_status(batch_dir: Path, universe_file: Path, batch_size: int) -> dict[str, object]:
    universe = pd.read_csv(universe_file)
    total_companies = len(universe)
    total_batches = (total_companies + batch_size - 1) // batch_size
    files = sorted(batch_dir.glob("factor_batch_*.csv"))
    completed_batches = sorted({batch_index_from_name(path) for path in files})
    company_ids: set[str] = set()
    row_count = 0
    for path in files:
        frame = pd.read_csv(path, usecols=lambda c: c in {"stock_id", "report_date"})
        row_count += len(frame)
        if "stock_id" in frame:
            company_ids.update(frame["stock_id"].astype(str))
    pending_batches = [index for index in range(total_batches) if index not in set(completed_batches)]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "universe_companies": total_companies,
        "batch_size": batch_size,
        "total_batches": total_batches,
        "completed_batches": completed_batches,
        "completed_batch_count": len(completed_batches),
        "pending_batch_count": len(pending_batches),
        "next_batch": pending_batches[0] if pending_batches else None,
        "companies_materialized": len(company_ids),
        "factor_rows": row_count,
        "universe_source": universe_file.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize durable full-universe factor batches into a publish directory.")
    parser.add_argument("--batch-dir", default=str(ROOT / "artifacts" / "factor_batches"))
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--manifest", default=str(ROOT / "artifacts" / "factor_cache_manifest.json"))
    parser.add_argument("--publish-dir", required=True)
    parser.add_argument("--merged-dataset", default=str(ROOT / "artifacts" / "factor_validation_full.csv"))
    args = parser.parse_args()

    source = Path(args.batch_dir)
    target = Path(args.publish_dir)
    batches_target = target / "batches"
    batches_target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(source.glob("factor_batch_*.csv")):
        shutil.copy2(path, batches_target / path.name)
        copied += 1

    merged = Path(args.merged_dataset)
    if merged.exists():
        shutil.copy2(merged, target / "factor_validation_full.csv")
    manifest = Path(args.manifest)
    if manifest.exists():
        shutil.copy2(manifest, target / "cache_manifest_latest.json")
    shutil.copy2(args.universe_file, target / "taiwan_stock_universe.csv")

    status = build_collection_status(batches_target, Path(args.universe_file), args.batch_size)
    (target / "collection_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "PERSISTENT_SNAPSHOT_OK",
        f"copied={copied}",
        f"completed_batches={status['completed_batch_count']}/{status['total_batches']}",
        f"companies={status['companies_materialized']}",
        f"rows={status['factor_rows']}",
        f"next_batch={status['next_batch']}",
    )


if __name__ == "__main__":
    main()
