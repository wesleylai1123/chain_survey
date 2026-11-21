"""Capture official Taiwan ETF/FX data or verify an offline frozen capture."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.multi_asset.official_capture import capture_official_data, load_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', default='0050,00981A')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--base-currency', choices=['TWD', 'USD'], default='TWD')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'artifacts/official-data')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    try:
        if args.replay:
            request, _ = load_capture(args.replay)
            print(f'OFFICIAL_REPLAY_OK assets={len(request["instruments"])} cutoff={request["as_of"]}')
        else:
            if not args.start or not args.end:
                parser.error('--start and --end are required for live collection')
            path = capture_official_data(args.symbols.split(','), args.start, args.end, args.output_dir,
                base_currency=args.base_currency)
            print(f'OFFICIAL_CAPTURE_OK manifest={path}')
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f'Official data operation failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
