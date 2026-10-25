"""Export the canonical Company × ABF report as JSON and an offline HTML view."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.abf_company_survey import build_company_survey
from core.abf_company_survey_html import render_company_survey


def export_company_survey(audit: dict, factor: pd.DataFrame, facts: list | dict, *,
                          as_of: str, output_dir: Path, input_paths: dict[str, Path] | None = None) -> dict:
    """Reuse an existing audit. No correlations or holdout choices are recomputed."""
    report = build_company_survey(audit, factor, facts, as_of=as_of)
    report['input_manifest'] = {name: dict(path=str(path),
        sha256=sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        data_status='AVAILABLE' if path.exists() else 'UNAVAILABLE')
        for name, path in (input_paths or {}).items()}
    report['code_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report['working_tree_dirty'] = bool(subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/'abf_company_survey.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (output_dir/'abf_company_survey.html').write_text(render_company_survey(report), encoding='utf-8')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=ROOT/'artifacts/abf_semantics_validation.json')
    parser.add_argument('--factor', type=Path, default=ROOT/'artifacts/factor_validation_dataset.csv')
    parser.add_argument('--facts', type=Path, default=ROOT/'data/abf_company_research_evidence.json')
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).isoformat())
    parser.add_argument('--output-dir', type=Path, default=ROOT/'artifacts')
    args = parser.parse_args(argv)
    audit = json.loads(args.audit.read_text(encoding='utf-8')) if args.audit.exists() else {}
    facts = json.loads(args.facts.read_text(encoding='utf-8')) if args.facts.exists() else []
    factor = pd.read_csv(args.factor, low_memory=False) if args.factor.exists() else pd.DataFrame()
    report = export_company_survey(audit, factor, facts, as_of=args.as_of, output_dir=args.output_dir,
        input_paths={'audit': args.audit, 'factor': args.factor, 'facts': args.facts})
    print('ABF_COMPANY_SURVEY_OK', len(report['companies']), 'companies',
          sum(len(c['primary_facts']) for c in report['companies']), 'reviewed facts')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
