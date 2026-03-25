from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.twse_ingestion import write_canonical_external_tables


if __name__ == "__main__":
    monthly_path, quarterly_path = write_canonical_external_tables()
    print(f"Wrote {monthly_path}")
    print(f"Wrote {quarterly_path}")
