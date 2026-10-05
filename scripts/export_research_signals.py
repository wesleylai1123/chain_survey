"""Export point-in-time ResearchSignalV1 records from a MOPS-derived CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_signal_export import DEFAULT_STOCK_IDS, MODEL_VERSION, _prepare


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="MOPS-derived monthly revenue CSV")
    parser.add_argument("--snapshot-acquired-at", required=True, help="Timezone-aware ISO acquisition timestamp")
    parser.add_argument("--as-of", required=True, help="Timezone-aware ISO knowledge cutoff")
    parser.add_argument("--commit-sha", required=True, help="Source code commit SHA")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON array path")
    parser.add_argument("--stock-ids", nargs="+", default=list(DEFAULT_STOCK_IDS), help="Four-digit company codes")
    args = parser.parse_args(argv)

    try:
        original = args.input.read_bytes()
        input_hash = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        required = {"company", "ticker", "period", "period_date", "published_at", "monthly_revenue", "yoy_pct", "source", "source_url", "knowledge_time_method", "transport"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"input CSV requires columns: {', '.join(sorted(required))}")
        records, diagnostics = _prepare(
            list(reader),
            snapshot_acquired_at=args.snapshot_acquired_at,
            as_of=args.as_of,
            commit_sha=args.commit_sha,
            input_snapshot_id=f"sha256:{input_hash}",
            stock_ids=args.stock_ids,
        )
        source_trace = f"source_file:{args.input};sha256:{input_hash}"
        for record in records:
            record["lineage"]["inputs"].append(source_trace)
        manifest = {
            "contract": "ResearchSignalV1",
            "schema_version": "1.0.0",
            "model_version": MODEL_VERSION,
            "input_file": str(args.input),
            "input_sha256": input_hash,
            "input_snapshot_id": f"sha256:{input_hash}",
            "snapshot_acquired_at": args.snapshot_acquired_at,
            "as_of": args.as_of,
            "commit_sha": args.commit_sha,
            "stock_ids": list(args.stock_ids),
            **diagnostics,
        }
        output = args.output
        manifest_path = output.with_suffix(".manifest.json")
        if output.resolve() in {args.input.resolve(), manifest_path.resolve()} or manifest_path.resolve() == args.input.resolve():
            raise ValueError("input, output, and manifest paths must be distinct")
        for target in (output, manifest_path):
            if target.exists() and not target.is_file():
                raise ValueError(f"output target is not a regular file: {target}")
        output.parent.mkdir(parents=True, exist_ok=True)
        temp_paths: list[Path] = []
        backup_path: Path | None = None
        output_replaced = False
        try:
            for target, payload in ((output, _json_bytes(records)), (manifest_path, _json_bytes(manifest))):
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as file:
                    file.write(payload)
                    temp_paths.append(Path(file.name))
            if output.exists():
                with tempfile.NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.backup.", suffix=".tmp", delete=False) as file:
                    backup_path = Path(file.name)
                shutil.copy2(output, backup_path)
            os.replace(temp_paths[0], output)
            output_replaced = True
            os.replace(temp_paths[1], manifest_path)
        except Exception:
            if output_replaced:
                if backup_path is not None:
                    os.replace(backup_path, output)
                else:
                    output.unlink()
            raise
        finally:
            for path in temp_paths:
                path.unlink(missing_ok=True)
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
        return 0
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
