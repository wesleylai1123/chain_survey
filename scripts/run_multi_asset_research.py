"""Main-product CLI: normalized input -> isolated metrics service -> context."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.multi_asset.adapters import load_csv_bundle, load_request
from core.multi_asset.context import build_research_context
from core.multi_asset.service import run_research
from core.multi_asset.official_capture import load_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-repo', type=Path)
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument('--csv-bundle', action='store_true')
    formats.add_argument('--official-capture', action='store_true')
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Input and output must be different files')
    if args.official_capture and args.output.resolve().is_relative_to(args.input.resolve().parent):
        parser.error('Output must be outside the immutable capture directory')
    loader = load_capture if args.official_capture else (load_csv_bundle if args.csv_bundle else load_request)
    request, lineage = loader(args.input)
    context = build_research_context(request)
    result = run_research(request, args.engine_repo)
    if any((args.input.parent / row['path']).resolve() == args.output.resolve()
           for row in lineage.get('files', {}).values()):
        parser.error('Output must not overwrite a bundle source CSV')
    report = dict(contract='MultiAssetResearchReportV1', schema_version='1.0.0',
        result=result, research_context=context, adapter_lineage=lineage)
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw.encode('utf-8'))
        os.replace(temporary, args.output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f'MULTI_ASSET_RESEARCH_OK assets={len(result["instruments"])} output={args.output}')


if __name__ == '__main__':
    main()
