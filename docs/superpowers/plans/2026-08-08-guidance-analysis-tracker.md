# Guidance & Product-Line Credibility Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let chain_survey track management guidance/product-line claims from earnings calls, verify them against actual quarterly financials already in the platform, and surface a credibility score + product-line signal in the desktop GUI.

**Architecture:** Three new CSV-backed datasets (`source_documents`, `guidance_claims`, `claim_outcomes`) follow the existing `data_loader.py` / `data_validation.py` schema-registry pattern. A new `core/guidance_service.py` provides CRUD for claims (mirrors `core/product_supply_chain_service.py`). A new `core/guidance_verification.py` is a pure rule-based engine that compares confirmed claims against `quarterly_financials.csv` and computes a per-company credibility score. A standalone script (`scripts/extract_guidance_claims.py`) uses the Claude API to turn a PDF earnings-call document into `pending_review` claims. Two additions to `app/gui_app.py` expose review and results: a new top-level "Guidance Review" tab, and a new "Guidance Tracker" sub-tab inside Company Explorer's existing relation notebook.

**Tech Stack:** Python 3.11+, pandas, tkinter/ttk (existing), `anthropic` SDK (new), `pdfplumber` (new), unittest (existing test convention).

## Global Constraints

- Spec: `chain_survey/docs/superpowers/specs/2026-08-08-guidance-analysis-design.md`.
- Companies in scope: only the 14 already in `data/company_master.csv`. No new-company onboarding.
- Verification uses only data already in `data/quarterly_financials.csv` (no monthly_revenue, no new external source).
- Period format is `<ROC year>Q<quarter>`, e.g. `114Q3`, matching the existing `quarterly_financials.csv` `period` column. Validate with `^\d+Q[1-4]$`.
- Every claim starts `status = pending_review` and only feeds verification/scoring once a human confirms it (`status = confirmed`). This gate is load-bearing — do not add a path that lets unreviewed claims influence the credibility score.
- Follow existing code conventions exactly: `from __future__ import annotations`, dataclass-free pandas-DataFrame services, `lru_cache`-backed loaders in `data_loader.py`, `data_loader.clear_data_caches()` called after every write, tests as `unittest.TestCase` under `tests/` using the tempdir + `patch.object(data_loader, "DATA_DIR", ...)` fixture pattern already used in `tests/test_product_supply_chain_management.py`.

---

### Task 1: Guidance Data Schemas & Loaders

**Files:**
- Modify: `chain_survey/core/data_validation.py`
- Modify: `chain_survey/core/data_loader.py`
- Modify: `chain_survey/data/data_model_manifest.json`
- Test: `chain_survey/tests/test_guidance_data_layer.py`

**Interfaces:**
- Consumes: `core.data_validation.validate_dataframe(dataset_id, df)` (existing), `core.data_loader.DATA_DIR` (existing), `core.data_loader._empty_dataframe(columns)` (existing).
- Produces (used by Tasks 2 and 3):
  - `data_loader.load_source_documents() -> pd.DataFrame` with columns `("doc_id", "ticker", "file_path", "source_quarter", "call_date")`.
  - `data_loader.load_guidance_claims() -> pd.DataFrame` with columns `("claim_id", "doc_id", "ticker", "source_quarter", "target_period", "category", "product_or_segment", "direction", "quant_low", "quant_high", "raw_text", "status", "reviewed_by", "reviewed_at")`.
  - `data_loader.load_claim_outcomes() -> pd.DataFrame` with columns `("claim_id", "actual_value", "match_result", "evaluated_at", "note")`.
  - All three return an empty (but correctly-columned) DataFrame if the backing CSV doesn't exist yet, matching `load_product_supply_chain_mappings()`'s existing pattern.
  - `data_loader.clear_data_caches()` also clears these three new caches.

- [ ] **Step 1: Write the failing test**

Create `chain_survey/tests/test_guidance_data_layer.py`:

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader


class GuidanceDataLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_loaders_return_empty_frames_with_correct_columns_when_files_missing(self) -> None:
        source_documents = data_loader.load_source_documents()
        self.assertEqual(
            list(source_documents.columns),
            ["doc_id", "ticker", "file_path", "source_quarter", "call_date"],
        )
        self.assertTrue(source_documents.empty)

        claims = data_loader.load_guidance_claims()
        self.assertEqual(
            list(claims.columns),
            [
                "claim_id",
                "doc_id",
                "ticker",
                "source_quarter",
                "target_period",
                "category",
                "product_or_segment",
                "direction",
                "quant_low",
                "quant_high",
                "raw_text",
                "status",
                "reviewed_by",
                "reviewed_at",
            ],
        )
        self.assertTrue(claims.empty)

        outcomes = data_loader.load_claim_outcomes()
        self.assertEqual(
            list(outcomes.columns),
            ["claim_id", "actual_value", "match_result", "evaluated_at", "note"],
        )
        self.assertTrue(outcomes.empty)

    def test_loaders_read_existing_csv_and_validate_columns(self) -> None:
        (self.data_dir / "source_documents.csv").write_text(
            "doc_id,ticker,file_path,source_quarter,call_date\n"
            "doc-1,2330.TW,data/raw_transcripts/2330.TW/114Q2.pdf,114Q2,2025-07-18\n",
            encoding="utf-8",
        )
        loaded = data_loader.load_source_documents()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["ticker"], "2330.TW")

    def test_clear_data_caches_clears_guidance_loaders(self) -> None:
        data_loader.load_guidance_claims()
        (self.data_dir / "guidance_claims.csv").write_text(
            "claim_id,doc_id,ticker,source_quarter,target_period,category,product_or_segment,"
            "direction,quant_low,quant_high,raw_text,status,reviewed_by,reviewed_at\n"
            "c-1,doc-1,2330.TW,114Q2,114Q3,revenue_growth,,up,10,15,\"rev up\",pending_review,,\n",
            encoding="utf-8",
        )
        data_loader.clear_data_caches()
        self.assertEqual(len(data_loader.load_guidance_claims()), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chain_survey && python -m pytest tests/test_guidance_data_layer.py -v`
Expected: FAIL with `AttributeError: module 'core.data_loader' has no attribute 'load_source_documents'`.

- [ ] **Step 3: Add schema entries to `core/data_validation.py`**

In `chain_survey/core/data_validation.py`, add three entries to `SCHEMA_REGISTRY` (insert after the `"quarterly_financials"` entry, before `"external_data_sources"`):

```python
    "source_documents": DatasetSchema(
        dataset_id="source_documents",
        required_columns=("doc_id", "ticker", "file_path", "source_quarter", "call_date"),
        primary_key=("doc_id",),
        description="Registry of ingested earnings call source documents (PDF decks/transcripts).",
    ),
    "guidance_claims": DatasetSchema(
        dataset_id="guidance_claims",
        required_columns=(
            "claim_id",
            "doc_id",
            "ticker",
            "source_quarter",
            "target_period",
            "category",
            "product_or_segment",
            "direction",
            "quant_low",
            "quant_high",
            "raw_text",
            "status",
            "reviewed_by",
            "reviewed_at",
        ),
        primary_key=("claim_id",),
        description="Structured forward-looking claims extracted from earnings call documents.",
    ),
    "claim_outcomes": DatasetSchema(
        dataset_id="claim_outcomes",
        required_columns=("claim_id", "actual_value", "match_result", "evaluated_at", "note"),
        primary_key=("claim_id",),
        description="Verification results comparing confirmed claims against actual financials.",
    ),
```

- [ ] **Step 4: Add loader functions to `core/data_loader.py`**

In `chain_survey/core/data_loader.py`, add after `load_quarterly_financials()`:

```python
@lru_cache(maxsize=1)
def load_source_documents() -> pd.DataFrame:
    path = DATA_DIR / "source_documents.csv"
    if not path.exists():
        return _empty_dataframe(("doc_id", "ticker", "file_path", "source_quarter", "call_date"))
    df = pd.read_csv(path)
    validate_dataframe("source_documents", df)
    return df


@lru_cache(maxsize=1)
def load_guidance_claims() -> pd.DataFrame:
    path = DATA_DIR / "guidance_claims.csv"
    if not path.exists():
        return _empty_dataframe(
            (
                "claim_id",
                "doc_id",
                "ticker",
                "source_quarter",
                "target_period",
                "category",
                "product_or_segment",
                "direction",
                "quant_low",
                "quant_high",
                "raw_text",
                "status",
                "reviewed_by",
                "reviewed_at",
            )
        )
    df = pd.read_csv(path)
    validate_dataframe("guidance_claims", df)
    return df


@lru_cache(maxsize=1)
def load_claim_outcomes() -> pd.DataFrame:
    path = DATA_DIR / "claim_outcomes.csv"
    if not path.exists():
        return _empty_dataframe(("claim_id", "actual_value", "match_result", "evaluated_at", "note"))
    df = pd.read_csv(path)
    validate_dataframe("claim_outcomes", df)
    return df
```

Then in `clear_data_caches()`, add three lines after `load_events.cache_clear()`:

```python
    load_source_documents.cache_clear()
    load_guidance_claims.cache_clear()
    load_claim_outcomes.cache_clear()
```

- [ ] **Step 5: Register the new datasets in the manifest**

In `chain_survey/data/data_model_manifest.json`, add three entries to the `"datasets"` array (after the `quarterly_financials` entry):

```json
    {
      "dataset_id": "source_documents",
      "file": "data/source_documents.csv",
      "description": "法說會來源文件登記表"
    },
    {
      "dataset_id": "guidance_claims",
      "file": "data/guidance_claims.csv",
      "description": "從法說會抽取的管理層前瞻聲明"
    },
    {
      "dataset_id": "claim_outcomes",
      "file": "data/claim_outcomes.csv",
      "description": "聲明與實際財報的對帳結果"
    }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd chain_survey && python -m pytest tests/test_guidance_data_layer.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 7: Commit**

```bash
cd chain_survey
git add core/data_validation.py core/data_loader.py data/data_model_manifest.json tests/test_guidance_data_layer.py
git commit -m "feat: add guidance claim data schemas and loaders

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Guidance Claim Service (CRUD + Review Workflow)

**Files:**
- Create: `chain_survey/core/guidance_service.py`
- Test: `chain_survey/tests/test_guidance_service.py`

**Interfaces:**
- Consumes: `core.data_loader.load_source_documents/load_guidance_claims/load_claim_outcomes/load_companies/clear_data_caches/DATA_DIR` (Task 1), `core.data_validation.validate_dataframe`.
- Produces (used by Task 3, Task 4, Task 5, Task 6):
  - `PERIOD_PATTERN: re.Pattern` and `parse_period(period: str) -> tuple[int, int]` — raises `ValueError` on non-matching input.
  - `register_source_document(*, ticker: str, file_path: str, source_quarter: str, call_date: str) -> dict` — returns the created row as a dict, including generated `doc_id`.
  - `load_source_documents() -> pd.DataFrame` (thin re-export).
  - `add_claim(*, doc_id: str, ticker: str, source_quarter: str, target_period: str, category: str, product_or_segment: str | None, direction: str, quant_low: float | None, quant_high: float | None, raw_text: str) -> dict` — returns created row as dict with generated `claim_id`, `status="pending_review"`.
  - `load_guidance_claims(status: str | None = None) -> pd.DataFrame` — optional status filter.
  - `update_claim(claim_id: str, **fields) -> dict` — only allowed while `status == "pending_review"`; raises `ValueError` otherwise or if `claim_id` not found.
  - `confirm_claim(claim_id: str, *, reviewed_by: str) -> dict` — sets `status="confirmed"`, stamps `reviewed_by`/`reviewed_at`.
  - `reject_claim(claim_id: str, *, reviewed_by: str) -> dict` — sets `status="rejected"`, stamps `reviewed_by`/`reviewed_at`.
  - `delete_claim(claim_id: str) -> None`.
  - `VALID_CATEGORIES = {"revenue_growth", "gross_margin", "product_line", "capex", "other"}`, `VALID_DIRECTIONS = {"up", "down", "flat"}`.

- [ ] **Step 1: Write the failing test**

Create `chain_survey/tests/test_guidance_service.py`:

```python
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core import guidance_service


class GuidanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        shutil.copy(ROOT / "data" / "company_master.csv", self.data_dir / "company_master.csv")

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def _register_doc(self) -> str:
        doc = guidance_service.register_source_document(
            ticker="2330.TW",
            file_path="data/raw_transcripts/2330.TW/114Q2.pdf",
            source_quarter="114Q2",
            call_date="2025-07-18",
        )
        return doc["doc_id"]

    def test_parse_period_accepts_valid_and_rejects_invalid(self) -> None:
        self.assertEqual(guidance_service.parse_period("114Q3"), (114, 3))
        with self.assertRaises(ValueError):
            guidance_service.parse_period("2025-Q3")

    def test_register_source_document_persists_and_reloads(self) -> None:
        doc_id = self._register_doc()
        reloaded = guidance_service.load_source_documents()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded.iloc[0]["doc_id"], doc_id)

    def test_add_claim_defaults_to_pending_review(self) -> None:
        doc_id = self._register_doc()
        claim = guidance_service.add_claim(
            doc_id=doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="revenue_growth",
            product_or_segment=None,
            direction="up",
            quant_low=10.0,
            quant_high=15.0,
            raw_text="We expect Q3 revenue to grow 10-15% sequentially.",
        )
        self.assertEqual(claim["status"], "pending_review")

        pending = guidance_service.load_guidance_claims(status="pending_review")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.iloc[0]["claim_id"], claim["claim_id"])

    def test_add_claim_rejects_unknown_ticker(self) -> None:
        doc_id = self._register_doc()
        with self.assertRaises(ValueError):
            guidance_service.add_claim(
                doc_id=doc_id,
                ticker="9999.TW",
                source_quarter="114Q2",
                target_period="114Q3",
                category="revenue_growth",
                product_or_segment=None,
                direction="up",
                quant_low=None,
                quant_high=None,
                raw_text="Unknown ticker claim.",
            )

    def test_add_claim_rejects_invalid_category_and_direction(self) -> None:
        doc_id = self._register_doc()
        with self.assertRaises(ValueError):
            guidance_service.add_claim(
                doc_id=doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                target_period="114Q3",
                category="not_a_category",
                product_or_segment=None,
                direction="up",
                quant_low=None,
                quant_high=None,
                raw_text="Bad category.",
            )
        with self.assertRaises(ValueError):
            guidance_service.add_claim(
                doc_id=doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                target_period="114Q3",
                category="revenue_growth",
                product_or_segment=None,
                direction="sideways",
                quant_low=None,
                quant_high=None,
                raw_text="Bad direction.",
            )

    def test_update_claim_only_allowed_while_pending(self) -> None:
        doc_id = self._register_doc()
        claim = guidance_service.add_claim(
            doc_id=doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="revenue_growth",
            product_or_segment=None,
            direction="up",
            quant_low=10.0,
            quant_high=15.0,
            raw_text="We expect Q3 revenue to grow 10-15% sequentially.",
        )
        updated = guidance_service.update_claim(claim["claim_id"], direction="flat", quant_low=None, quant_high=None)
        self.assertEqual(updated["direction"], "flat")

        guidance_service.confirm_claim(claim["claim_id"], reviewed_by="analyst")
        with self.assertRaises(ValueError):
            guidance_service.update_claim(claim["claim_id"], direction="down")

    def test_confirm_and_reject_stamp_reviewer_and_timestamp(self) -> None:
        doc_id = self._register_doc()
        claim = guidance_service.add_claim(
            doc_id=doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="product_line",
            product_or_segment="Advanced Packaging",
            direction="up",
            quant_low=None,
            quant_high=None,
            raw_text="Advanced packaging demand remains strong.",
        )
        confirmed = guidance_service.confirm_claim(claim["claim_id"], reviewed_by="analyst")
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["reviewed_by"], "analyst")
        self.assertTrue(confirmed["reviewed_at"])

        claim2 = guidance_service.add_claim(
            doc_id=doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="capex",
            product_or_segment=None,
            direction="up",
            quant_low=None,
            quant_high=None,
            raw_text="Capex will increase next quarter.",
        )
        rejected = guidance_service.reject_claim(claim2["claim_id"], reviewed_by="analyst")
        self.assertEqual(rejected["status"], "rejected")

    def test_delete_claim_removes_row(self) -> None:
        doc_id = self._register_doc()
        claim = guidance_service.add_claim(
            doc_id=doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="other",
            product_or_segment=None,
            direction="flat",
            quant_low=None,
            quant_high=None,
            raw_text="Nothing notable.",
        )
        guidance_service.delete_claim(claim["claim_id"])
        self.assertTrue(guidance_service.load_guidance_claims().empty)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chain_survey && python -m pytest tests/test_guidance_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.guidance_service'`.

- [ ] **Step 3: Write `core/guidance_service.py`**

Create `chain_survey/core/guidance_service.py`:

```python
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pandas as pd

from core import data_loader
from core.data_validation import validate_dataframe

VALID_CATEGORIES = {"revenue_growth", "gross_margin", "product_line", "capex", "other"}
VALID_DIRECTIONS = {"up", "down", "flat"}
VALID_STATUSES = {"pending_review", "confirmed", "rejected"}

PERIOD_PATTERN = re.compile(r"^(\d+)Q([1-4])$")

SOURCE_DOCUMENT_COLUMNS = ("doc_id", "ticker", "file_path", "source_quarter", "call_date")
GUIDANCE_CLAIM_COLUMNS = (
    "claim_id",
    "doc_id",
    "ticker",
    "source_quarter",
    "target_period",
    "category",
    "product_or_segment",
    "direction",
    "quant_low",
    "quant_high",
    "raw_text",
    "status",
    "reviewed_by",
    "reviewed_at",
)


def parse_period(period: str) -> tuple[int, int]:
    match = PERIOD_PATTERN.match(str(period))
    if not match:
        raise ValueError(f"Invalid period format: '{period}', expected e.g. '114Q3'")
    return int(match.group(1)), int(match.group(2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _known_tickers() -> set[str]:
    return set(data_loader.load_companies()["ticker"].astype(str))


# ---------------------------------------------------------------------------
# source_documents
# ---------------------------------------------------------------------------

def load_source_documents() -> pd.DataFrame:
    return data_loader.load_source_documents()


def register_source_document(*, ticker: str, file_path: str, source_quarter: str, call_date: str) -> dict[str, object]:
    if ticker not in _known_tickers():
        raise ValueError(f"Unknown ticker: '{ticker}'")
    parse_period(source_quarter)
    if not file_path.strip():
        raise ValueError("file_path cannot be empty")

    row = {
        "doc_id": uuid.uuid4().hex[:12],
        "ticker": ticker,
        "file_path": file_path,
        "source_quarter": source_quarter,
        "call_date": call_date,
    }
    current = load_source_documents()
    combined = pd.concat([current, pd.DataFrame([row])], ignore_index=True) if not current.empty else pd.DataFrame([row])
    validate_dataframe("source_documents", combined)
    combined.to_csv(data_loader.DATA_DIR / "source_documents.csv", index=False)
    data_loader.clear_data_caches()
    return row


# ---------------------------------------------------------------------------
# guidance_claims
# ---------------------------------------------------------------------------

def load_guidance_claims(status: str | None = None) -> pd.DataFrame:
    df = data_loader.load_guidance_claims()
    if status is not None and not df.empty:
        df = df[df["status"] == status].copy()
    return df


def _validate_claim_fields(
    *,
    ticker: str,
    source_quarter: str,
    target_period: str,
    category: str,
    direction: str,
    quant_low: float | None,
    quant_high: float | None,
    raw_text: str,
) -> None:
    if ticker not in _known_tickers():
        raise ValueError(f"Unknown ticker: '{ticker}'")
    parse_period(source_quarter)
    parse_period(target_period)
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}', expected one of {sorted(VALID_CATEGORIES)}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Invalid direction '{direction}', expected one of {sorted(VALID_DIRECTIONS)}")
    if quant_low is not None and quant_high is not None and float(quant_low) > float(quant_high):
        raise ValueError("quant_low cannot be greater than quant_high")
    if not raw_text.strip():
        raise ValueError("raw_text cannot be empty")


def add_claim(
    *,
    doc_id: str,
    ticker: str,
    source_quarter: str,
    target_period: str,
    category: str,
    product_or_segment: str | None,
    direction: str,
    quant_low: float | None,
    quant_high: float | None,
    raw_text: str,
) -> dict[str, object]:
    _validate_claim_fields(
        ticker=ticker,
        source_quarter=source_quarter,
        target_period=target_period,
        category=category,
        direction=direction,
        quant_low=quant_low,
        quant_high=quant_high,
        raw_text=raw_text,
    )

    row = {
        "claim_id": uuid.uuid4().hex[:12],
        "doc_id": doc_id,
        "ticker": ticker,
        "source_quarter": source_quarter,
        "target_period": target_period,
        "category": category,
        "product_or_segment": product_or_segment or "",
        "direction": direction,
        "quant_low": quant_low,
        "quant_high": quant_high,
        "raw_text": raw_text.strip(),
        "status": "pending_review",
        "reviewed_by": "",
        "reviewed_at": "",
    }
    _append_claim_row(row)
    return row


def _append_claim_row(row: dict[str, object]) -> None:
    current = data_loader.load_guidance_claims()
    combined = pd.concat([current, pd.DataFrame([row])], ignore_index=True) if not current.empty else pd.DataFrame([row])
    validate_dataframe("guidance_claims", combined)
    combined.to_csv(data_loader.DATA_DIR / "guidance_claims.csv", index=False)
    data_loader.clear_data_caches()


def _get_claim_row(claim_id: str) -> pd.Series:
    claims = data_loader.load_guidance_claims()
    matches = claims[claims["claim_id"] == claim_id]
    if matches.empty:
        raise ValueError(f"No claim found with claim_id '{claim_id}'")
    return matches.iloc[0]


def _write_all_claims(df: pd.DataFrame) -> None:
    validate_dataframe("guidance_claims", df)
    df.to_csv(data_loader.DATA_DIR / "guidance_claims.csv", index=False)
    data_loader.clear_data_caches()


def update_claim(claim_id: str, **fields: object) -> dict[str, object]:
    current_row = _get_claim_row(claim_id)
    if current_row["status"] != "pending_review":
        raise ValueError(f"Claim '{claim_id}' is '{current_row['status']}' and can no longer be edited")

    updated = current_row.to_dict()
    updated.update(fields)
    _validate_claim_fields(
        ticker=str(updated["ticker"]),
        source_quarter=str(updated["source_quarter"]),
        target_period=str(updated["target_period"]),
        category=str(updated["category"]),
        direction=str(updated["direction"]),
        quant_low=updated.get("quant_low"),
        quant_high=updated.get("quant_high"),
        raw_text=str(updated["raw_text"]),
    )

    claims = data_loader.load_guidance_claims()
    claims.loc[claims["claim_id"] == claim_id, list(updated.keys())] = list(updated.values())
    _write_all_claims(claims)
    return updated


def confirm_claim(claim_id: str, *, reviewed_by: str) -> dict[str, object]:
    return _set_review_status(claim_id, status="confirmed", reviewed_by=reviewed_by)


def reject_claim(claim_id: str, *, reviewed_by: str) -> dict[str, object]:
    return _set_review_status(claim_id, status="rejected", reviewed_by=reviewed_by)


def _set_review_status(claim_id: str, *, status: str, reviewed_by: str) -> dict[str, object]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'")
    current_row = _get_claim_row(claim_id)
    if current_row["status"] != "pending_review":
        raise ValueError(f"Claim '{claim_id}' is already '{current_row['status']}'")

    claims = data_loader.load_guidance_claims()
    mask = claims["claim_id"] == claim_id
    claims.loc[mask, "status"] = status
    claims.loc[mask, "reviewed_by"] = reviewed_by
    claims.loc[mask, "reviewed_at"] = _now_iso()
    _write_all_claims(claims)
    return claims.loc[mask].iloc[0].to_dict()


def delete_claim(claim_id: str) -> None:
    claims = data_loader.load_guidance_claims()
    mask = claims["claim_id"] == claim_id
    if not mask.any():
        raise ValueError(f"No claim found with claim_id '{claim_id}'")
    remaining = claims.loc[~mask].reset_index(drop=True)
    if remaining.empty:
        remaining = pd.DataFrame(columns=list(GUIDANCE_CLAIM_COLUMNS))
    _write_all_claims(remaining)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chain_survey && python -m pytest tests/test_guidance_service.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd chain_survey
git add core/guidance_service.py tests/test_guidance_service.py
git commit -m "feat: add guidance claim CRUD and review-status service

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Verification Engine & Credibility Scoring

**Files:**
- Create: `chain_survey/core/guidance_verification.py`
- Test: `chain_survey/tests/test_guidance_verification.py`

**Interfaces:**
- Consumes: `core.data_loader.load_quarterly_financials/load_guidance_claims/load_claim_outcomes/DATA_DIR/clear_data_caches` (Task 1), `core.guidance_service.parse_period` (Task 2).
- Produces (used by Task 6 GUI):
  - `FLAT_THRESHOLD_PCT = 1.0`
  - `MATCH_SCORE = {"match": 1.0, "partial": 0.5, "miss": 0.0}`
  - `evaluate_claim(claim: pd.Series) -> tuple[str, float | None, str]` — returns `(match_result, actual_value, note)` where `match_result` is one of `"match"/"partial"/"miss"/"unverifiable"`.
  - `run_verification() -> pd.DataFrame` — recomputes `claim_outcomes.csv` from scratch for every `confirmed` claim, returns the resulting DataFrame.
  - `compute_credibility_score(ticker: str, trailing_quarters: int = 8) -> float | None` — `None` when there's no resolved (non-`unverifiable`) claim in the trailing window.

- [ ] **Step 1: Write the failing test**

Create `chain_survey/tests/test_guidance_verification.py`:

```python
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core import guidance_service
from core import guidance_verification


class GuidanceVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        shutil.copy(ROOT / "data" / "company_master.csv", self.data_dir / "company_master.csv")

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

        self._write_quarterly_financials()
        self.doc_id = guidance_service.register_source_document(
            ticker="2330.TW",
            file_path="data/raw_transcripts/2330.TW/114Q2.pdf",
            source_quarter="114Q2",
            call_date="2025-07-18",
        )["doc_id"]

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def _write_quarterly_financials(self) -> None:
        header = (
            "company,ticker,period,revenue,gross_profit,operating_income,pre_tax_income,"
            "net_income,eps,total_assets,total_liabilities,total_equity,book_value_per_share,"
            "source_date,source\n"
        )
        # 114Q2 revenue=1000 margin=50%% ; 114Q3 revenue=1150 (+15%%) margin=52%% (+2pp)
        rows = (
            "台積電,2330.TW,114Q2,1000,500,400,410,380,10,5000,2000,3000,100,20250718,test\n"
            "台積電,2330.TW,114Q3,1150,598,470,480,440,11,5200,2100,3100,102,20251018,test\n"
        )
        (self.data_dir / "quarterly_financials.csv").write_text(header + rows, encoding="utf-8")
        data_loader.clear_data_caches()

    def _confirmed_claim(self, **overrides: object) -> dict[str, object]:
        defaults = dict(
            doc_id=self.doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="revenue_growth",
            product_or_segment=None,
            direction="up",
            quant_low=10.0,
            quant_high=15.0,
            raw_text="We expect Q3 revenue to grow 10-15%% sequentially.",
        )
        defaults.update(overrides)
        claim = guidance_service.add_claim(**defaults)
        return guidance_service.confirm_claim(claim["claim_id"], reviewed_by="analyst")

    def test_revenue_growth_claim_within_range_matches(self) -> None:
        claim = self._confirmed_claim()
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "match")
        self.assertAlmostEqual(actual_value, 15.0, places=1)

    def test_revenue_growth_claim_right_direction_outside_range_is_partial(self) -> None:
        claim = self._confirmed_claim(quant_low=1.0, quant_high=5.0)
        result, _actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "partial")

    def test_revenue_growth_claim_wrong_direction_misses(self) -> None:
        claim = self._confirmed_claim(direction="down", quant_low=None, quant_high=None)
        result, _actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "miss")

    def test_product_line_claim_uses_directional_proxy(self) -> None:
        claim = self._confirmed_claim(
            category="product_line",
            product_or_segment="Advanced Packaging",
            direction="up",
            quant_low=None,
            quant_high=None,
        )
        result, _actual_value, note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "match")
        self.assertIn("revenue and margin", note)

    def test_capex_claim_is_unverifiable(self) -> None:
        claim = self._confirmed_claim(category="capex", quant_low=None, quant_high=None)
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "unverifiable")
        self.assertIsNone(actual_value)

    def test_run_verification_writes_outcomes_for_all_confirmed_claims(self) -> None:
        self._confirmed_claim()
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)

        outcomes = guidance_verification.run_verification()
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(set(outcomes["match_result"]), {"match", "unverifiable"})

        reloaded = data_loader.load_claim_outcomes()
        self.assertEqual(len(reloaded), 2)

    def test_compute_credibility_score_averages_resolved_outcomes(self) -> None:
        self._confirmed_claim()  # match -> 1.0
        self._confirmed_claim(direction="down", quant_low=None, quant_high=None)  # miss -> 0.0
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)  # unverifiable -> excluded
        guidance_verification.run_verification()

        score = guidance_verification.compute_credibility_score("2330.TW")
        self.assertAlmostEqual(score, 0.5, places=2)

    def test_compute_credibility_score_returns_none_when_nothing_resolved(self) -> None:
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)
        guidance_verification.run_verification()
        self.assertIsNone(guidance_verification.compute_credibility_score("2330.TW"))


def _as_series(row: dict[str, object]):
    import pandas as pd

    return pd.Series(row)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chain_survey && python -m pytest tests/test_guidance_verification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.guidance_verification'`.

- [ ] **Step 3: Write `core/guidance_verification.py`**

Create `chain_survey/core/guidance_verification.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from core import data_loader
from core.guidance_service import parse_period

CATEGORY_DIRECT_FIELD = {"revenue_growth": "revenue", "gross_margin": "gross_margin"}
FLAT_THRESHOLD_PCT = 1.0
MATCH_SCORE = {"match": 1.0, "partial": 0.5, "miss": 0.0}
CLAIM_OUTCOME_COLUMNS = ("claim_id", "actual_value", "match_result", "evaluated_at", "note")


def _financials_for_ticker(ticker: str) -> pd.DataFrame:
    df = data_loader.load_quarterly_financials()
    subset = df[df["ticker"] == ticker].copy()
    if subset.empty:
        return subset
    subset["gross_margin"] = (subset["gross_profit"] / subset["revenue"] * 100).round(2)
    subset = subset.sort_values("period", key=lambda periods: periods.map(lambda p: parse_period(p))).reset_index(drop=True)
    return subset


def _qoq_change(subset: pd.DataFrame, target_period: str, field: str) -> float | None:
    matches = subset.index[subset["period"] == target_period]
    if len(matches) == 0:
        return None
    pos = matches[0]
    if pos == 0:
        return None
    current = subset.loc[pos, field]
    previous = subset.loc[pos - 1, field]
    if field == "revenue":
        if previous == 0:
            return None
        return round((current - previous) / abs(previous) * 100, 2)
    return round(current - previous, 2)


def _direction_matches(actual_change: float, direction: str) -> bool:
    if direction == "flat":
        return abs(actual_change) <= FLAT_THRESHOLD_PCT
    if direction == "up":
        return actual_change > FLAT_THRESHOLD_PCT
    if direction == "down":
        return actual_change < -FLAT_THRESHOLD_PCT
    raise ValueError(f"Invalid direction '{direction}'")


def evaluate_claim(claim: pd.Series) -> tuple[str, float | None, str]:
    ticker = str(claim["ticker"])
    category = str(claim["category"])
    target_period = str(claim["target_period"])
    direction = str(claim["direction"])
    subset = _financials_for_ticker(ticker)

    if category in CATEGORY_DIRECT_FIELD:
        field = CATEGORY_DIRECT_FIELD[category]
        change = _qoq_change(subset, target_period, field)
        if change is None:
            return "unverifiable", None, f"no resolvable QoQ baseline for {ticker} {target_period}"

        direction_ok = _direction_matches(change, direction)
        quant_low, quant_high = claim.get("quant_low"), claim.get("quant_high")
        has_range = pd.notna(quant_low) and pd.notna(quant_high)
        if not direction_ok:
            return "miss", change, "actual direction did not match claimed direction"
        if has_range and not (float(quant_low) <= change <= float(quant_high)):
            return "partial", change, "direction correct, actual value outside claimed range"
        return "match", change, "direction and range consistent" if has_range else "direction consistent"

    if category == "product_line":
        revenue_change = _qoq_change(subset, target_period, "revenue")
        margin_change = _qoq_change(subset, target_period, "gross_margin")
        if revenue_change is None or margin_change is None:
            return "unverifiable", None, "insufficient QoQ baseline for product-line proxy"

        agreements = sum(
            1 for change in (revenue_change, margin_change) if _direction_matches(change, direction)
        )
        if agreements == 2:
            return "match", revenue_change, "revenue and margin trend both corroborate claim"
        if agreements == 1:
            return "partial", revenue_change, "only one of revenue/margin trend corroborates claim"
        return "miss", revenue_change, "neither revenue nor margin trend corroborates claim"

    return "unverifiable", None, f"category '{category}' has no defined actual-data mapping"


def run_verification() -> pd.DataFrame:
    claims = data_loader.load_guidance_claims()
    confirmed = claims[claims["status"] == "confirmed"] if not claims.empty else claims

    if confirmed.empty:
        outcomes = pd.DataFrame(columns=list(CLAIM_OUTCOME_COLUMNS))
    else:
        evaluated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        records = []
        for _, claim in confirmed.iterrows():
            match_result, actual_value, note = evaluate_claim(claim)
            records.append(
                {
                    "claim_id": claim["claim_id"],
                    "actual_value": actual_value,
                    "match_result": match_result,
                    "evaluated_at": evaluated_at,
                    "note": note,
                }
            )
        outcomes = pd.DataFrame(records)

    outcomes.to_csv(data_loader.DATA_DIR / "claim_outcomes.csv", index=False)
    data_loader.clear_data_caches()
    return outcomes


def compute_credibility_score(ticker: str, trailing_quarters: int = 8) -> float | None:
    claims = data_loader.load_guidance_claims()
    if claims.empty:
        return None
    confirmed = claims[(claims["ticker"] == ticker) & (claims["status"] == "confirmed")]
    if confirmed.empty:
        return None

    distinct_quarters = sorted({str(q) for q in confirmed["source_quarter"]}, key=parse_period)
    window = set(distinct_quarters[-trailing_quarters:])
    windowed_claims = confirmed[confirmed["source_quarter"].isin(window)]
    if windowed_claims.empty:
        return None

    outcomes = data_loader.load_claim_outcomes()
    if outcomes.empty:
        return None
    merged = windowed_claims.merge(outcomes, on="claim_id", how="inner")
    resolved = merged[merged["match_result"].isin(MATCH_SCORE)]
    if resolved.empty:
        return None
    return round(float(resolved["match_result"].map(MATCH_SCORE).mean()), 3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chain_survey && python -m pytest tests/test_guidance_verification.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd chain_survey
git add core/guidance_verification.py tests/test_guidance_verification.py
git commit -m "feat: add guidance claim verification engine and credibility scoring

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: LLM Extraction Script

**Files:**
- Create: `chain_survey/scripts/extract_guidance_claims.py`
- Modify: `chain_survey/requirements.txt`
- Test: `chain_survey/tests/test_extract_guidance_claims.py`

**Interfaces:**
- Consumes: `core.guidance_service.register_source_document/add_claim` (Task 2).
- Produces:
  - `extract_text_from_pdf(path: Path) -> str`
  - `build_extraction_prompt(transcript_text: str) -> str`
  - `parse_llm_response(raw_text: str) -> list[dict]` — raises `ValueError` on malformed JSON; strips ` ```json ` fences if present.
  - `extract_claims_for_document(client, *, doc_id: str, ticker: str, source_quarter: str, pdf_path: Path, model: str = "claude-sonnet-5") -> int` — returns count of claims added.
  - `main(argv: list[str] | None = None) -> None` — CLI entrypoint (`--ticker`, `--source-quarter`, `--pdf-path`, `--call-date`).

This task's LLM call is not covered by an assertion on real model output (non-deterministic, requires network/API key) — per the design spec, extraction correctness is validated manually against real PDFs. The automated tests instead cover the deterministic logic: prompt parsing and the orchestration that turns a parsed response into stored claims, using a fake API client.

- [ ] **Step 1: Add new dependencies**

In `chain_survey/requirements.txt`, add:

```
anthropic>=0.40
pdfplumber>=0.11
```

Run: `cd chain_survey && pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

Create `chain_survey/tests/test_extract_guidance_claims.py`:

```python
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core import guidance_service
from scripts import extract_guidance_claims


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeMessagesClient:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_call_kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> FakeMessage:
        self.last_call_kwargs = kwargs
        return FakeMessage(self._response_text)


class FakeAnthropicClient:
    def __init__(self, response_text: str) -> None:
        self.messages = FakeMessagesClient(response_text)


class ExtractGuidanceClaimsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        shutil.copy(ROOT / "data" / "company_master.csv", self.data_dir / "company_master.csv")

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

        self.doc_id = guidance_service.register_source_document(
            ticker="2330.TW",
            file_path="data/raw_transcripts/2330.TW/114Q2.pdf",
            source_quarter="114Q2",
            call_date="2025-07-18",
        )["doc_id"]

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_parse_llm_response_handles_plain_json(self) -> None:
        raw_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "revenue up 10-15%%"}]'
        )
        parsed = extract_guidance_claims.parse_llm_response(raw_text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "revenue_growth")

    def test_parse_llm_response_strips_markdown_fences(self) -> None:
        raw_text = '```json\n[{"target_period": "114Q3", "category": "capex", ' \
            '"product_or_segment": null, "direction": "up", "quant_low": null, ' \
            '"quant_high": null, "raw_text": "capex increases"}]\n```'
        parsed = extract_guidance_claims.parse_llm_response(raw_text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["category"], "capex")

    def test_parse_llm_response_rejects_non_json(self) -> None:
        with self.assertRaises(ValueError):
            extract_guidance_claims.parse_llm_response("not json at all")

    def test_extract_claims_for_document_stores_pending_claims(self) -> None:
        response_text = (
            '[{"target_period": "114Q3", "category": "revenue_growth", '
            '"product_or_segment": null, "direction": "up", "quant_low": 10, '
            '"quant_high": 15, "raw_text": "We expect Q3 revenue to grow 10-15%% sequentially."},'
            '{"target_period": "114Q3", "category": "product_line", '
            '"product_or_segment": "Advanced Packaging", "direction": "up", '
            '"quant_low": null, "quant_high": null, "raw_text": "Advanced packaging demand is strong."}]'
        )
        fake_client = FakeAnthropicClient(response_text)

        with patch.object(extract_guidance_claims, "extract_text_from_pdf", return_value="fake transcript text"):
            count = extract_guidance_claims.extract_claims_for_document(
                fake_client,
                doc_id=self.doc_id,
                ticker="2330.TW",
                source_quarter="114Q2",
                pdf_path=Path("fake.pdf"),
            )

        self.assertEqual(count, 2)
        pending = guidance_service.load_guidance_claims(status="pending_review")
        self.assertEqual(len(pending), 2)
        self.assertIn("revenue_growth", pending["category"].tolist())
        self.assertIn("product_line", pending["category"].tolist())
        self.assertEqual(fake_client.messages.last_call_kwargs["model"], "claude-sonnet-5")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd chain_survey && python -m pytest tests/test_extract_guidance_claims.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.extract_guidance_claims'` (or `scripts` package missing).

- [ ] **Step 4: Write `scripts/extract_guidance_claims.py`**

Create `chain_survey/scripts/__init__.py` (empty file, makes `scripts` importable):

```python
```

Create `chain_survey/scripts/extract_guidance_claims.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import guidance_service

EXTRACTION_PROMPT_TEMPLATE = """You are extracting forward-looking claims from a Taiwan-listed company's earnings call transcript.

Only extract statements that describe expectations for a FUTURE reporting period (guidance, product-line outlook). Do not extract statements that merely restate already-published historical results.

Return a JSON array. Each element must have exactly these fields:
- "target_period": the future quarter the claim is about, formatted like "114Q3" (ROC year + quarter). Infer this from context if not stated explicitly.
- "category": one of "revenue_growth", "gross_margin", "product_line", "capex", "other"
- "product_or_segment": the product line or segment name if the claim is about one, otherwise null
- "direction": one of "up", "down", "flat"
- "quant_low": the low end of any quantitative range management gave, as a number, otherwise null
- "quant_high": the high end of any quantitative range management gave, as a number, otherwise null
- "raw_text": the verbatim excerpt this claim was extracted from

Return ONLY the JSON array, no other text.

Transcript:
{transcript_text}
"""


def extract_text_from_pdf(path: Path) -> str:
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return "\n".join(pages_text)


def build_extraction_prompt(transcript_text: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(transcript_text=transcript_text)


def parse_llm_response(raw_text: str) -> list[dict]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json"):]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("LLM response must be a JSON array of claims")
    return parsed


def extract_claims_for_document(
    client,
    *,
    doc_id: str,
    ticker: str,
    source_quarter: str,
    pdf_path: Path,
    model: str = "claude-sonnet-5",
) -> int:
    transcript_text = extract_text_from_pdf(pdf_path)
    prompt = build_extraction_prompt(transcript_text)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = response.content[0].text
    parsed_claims = parse_llm_response(raw_text)

    count = 0
    for parsed in parsed_claims:
        guidance_service.add_claim(
            doc_id=doc_id,
            ticker=ticker,
            source_quarter=source_quarter,
            target_period=parsed["target_period"],
            category=parsed["category"],
            product_or_segment=parsed.get("product_or_segment"),
            direction=parsed["direction"],
            quant_low=parsed.get("quant_low"),
            quant_high=parsed.get("quant_high"),
            raw_text=parsed["raw_text"],
        )
        count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract guidance claims from an earnings call PDF via the Claude API.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--source-quarter", required=True, help="Quarter the call was held for, e.g. 114Q2")
    parser.add_argument("--pdf-path", required=True, type=Path)
    parser.add_argument("--call-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args(argv)

    import anthropic

    client = anthropic.Anthropic()

    doc = guidance_service.register_source_document(
        ticker=args.ticker,
        file_path=str(args.pdf_path),
        source_quarter=args.source_quarter,
        call_date=args.call_date,
    )
    count = extract_claims_for_document(
        client,
        doc_id=doc["doc_id"],
        ticker=args.ticker,
        source_quarter=args.source_quarter,
        pdf_path=args.pdf_path,
        model=args.model,
    )
    print(f"Extracted {count} pending claim(s) from {args.pdf_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd chain_survey && python -m pytest tests/test_extract_guidance_claims.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Manual validation against a real PDF (not automated)**

Once you have a real earnings-call PDF and an `ANTHROPIC_API_KEY` set, run:

```bash
cd chain_survey
python scripts/extract_guidance_claims.py --ticker 2330.TW --source-quarter 114Q2 --pdf-path data/raw_transcripts/2330.TW/114Q2.pdf --call-date 2025-07-18
```

Confirm the printed count is sane and inspect `data/guidance_claims.csv` for extraction quality before relying on it. Note any prompt adjustments needed as follow-up — do not silently tune the prompt without re-checking a sample.

- [ ] **Step 7: Commit**

```bash
cd chain_survey
git add scripts/__init__.py scripts/extract_guidance_claims.py requirements.txt tests/test_extract_guidance_claims.py
git commit -m "feat: add Claude-based earnings call guidance extraction script

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: GUI — Guidance Review Tab

**Files:**
- Modify: `chain_survey/app/gui_app.py`

**Interfaces:**
- Consumes: `core.guidance_service.load_guidance_claims/update_claim/confirm_claim/reject_claim` (Task 2).
- Produces: a new top-level notebook tab; no other module depends on this tab's internals.

This task has no automated test — GUI behavior in this codebase is validated manually by running the app (see `chain_survey/tests/` — there is no existing test file exercising `gui_app.py`, consistent with the design spec's testing section).

- [ ] **Step 1: Add the import**

In `chain_survey/app/gui_app.py`, add to the imports (after the `product_supply_chain_service` import on line 37):

```python
from core.guidance_service import confirm_claim, load_guidance_claims, reject_claim, update_claim
```

- [ ] **Step 2: Register the new tab**

In `_build_layout` (around line 119-135), add the new tab frame and registration:

```python
        self.overview_tab = ttk.Frame(notebook, padding=14)
        self.company_tab = ttk.Frame(notebook, padding=14)
        self.manage_tab = ttk.Frame(notebook, padding=14)
        self.review_tab = ttk.Frame(notebook, padding=14)
        self.event_tab = ttk.Frame(notebook, padding=14)
        self.graph_tab = ttk.Frame(notebook, padding=14)

        notebook.add(self.overview_tab, text="Overview")
        notebook.add(self.company_tab, text="Company Explorer")
        notebook.add(self.manage_tab, text="Supply Chain Editor")
        notebook.add(self.review_tab, text="Guidance Review")
        notebook.add(self.event_tab, text="Event Simulator")
        notebook.add(self.graph_tab, text="Network Graph")

        self._build_overview_tab()
        self._build_company_tab()
        self._build_management_tab()
        self._build_review_tab()
        self._build_event_tab()
        self._build_graph_tab()
```

(This replaces the existing block of the same span — same five original lines plus the three `review_tab` additions.)

- [ ] **Step 3: Build the tab**

Add a new method, placed after `_build_management_tab` (after line 357, before `_build_event_tab`):

```python
    def _build_review_tab(self) -> None:
        controls = ttk.Frame(self.review_tab)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Button(controls, text="Refresh Queue", command=self.refresh_review_view).pack(side="left")

        body = ttk.Frame(self.review_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        queue_box = ttk.LabelFrame(body, text="Pending Claims", padding=12)
        queue_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.review_queue_tree = self._create_tree(
            queue_box,
            ("claim_id", "ticker", "source_quarter", "target_period", "category", "product_or_segment", "direction", "quant_low", "quant_high"),
        )
        self.review_queue_tree.bind("<<TreeviewSelect>>", self._on_review_claim_selected)

        detail_box = ttk.LabelFrame(body, text="Claim Detail", padding=12)
        detail_box.grid(row=0, column=1, sticky="nsew")

        ttk.Label(detail_box, text="Raw Text", style="Subhead.TLabel").pack(anchor="w")
        self.review_raw_text = tk.Text(detail_box, height=8, wrap="word")
        self.review_raw_text.pack(fill="both", expand=True, pady=(4, 12))
        self.review_raw_text.configure(state="disabled")

        form = ttk.Frame(detail_box)
        form.pack(fill="x")
        for idx in range(2):
            form.columnconfigure(idx, weight=1)

        ttk.Label(form, text="Category").grid(row=0, column=0, sticky="w")
        self.review_category_var = tk.StringVar()
        ttk.Combobox(
            form,
            textvariable=self.review_category_var,
            values=("revenue_growth", "gross_margin", "product_line", "capex", "other"),
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Direction").grid(row=0, column=1, sticky="w")
        self.review_direction_var = tk.StringVar()
        ttk.Combobox(
            form,
            textvariable=self.review_direction_var,
            values=("up", "down", "flat"),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(form, text="Product / Segment").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.review_product_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.review_product_var).grid(row=3, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(form, text="Quant Low / High").grid(row=2, column=1, sticky="w", pady=(10, 0))
        quant_frame = ttk.Frame(form)
        quant_frame.grid(row=3, column=1, sticky="ew")
        self.review_quant_low_var = tk.StringVar()
        self.review_quant_high_var = tk.StringVar()
        ttk.Entry(quant_frame, textvariable=self.review_quant_low_var, width=8).pack(side="left")
        ttk.Entry(quant_frame, textvariable=self.review_quant_high_var, width=8).pack(side="left", padx=(6, 0))

        button_row = ttk.Frame(detail_box)
        button_row.pack(fill="x", pady=(12, 0))
        ttk.Button(button_row, text="Save Edits", command=self._save_review_edits).pack(side="left")
        ttk.Button(button_row, text="Confirm", command=self._confirm_selected_claim).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Reject", command=self._reject_selected_claim).pack(side="left", padx=(8, 0))

        self.review_selected_claim_id: str | None = None
```

- [ ] **Step 4: Add refresh/selection/action methods**

Add after `_delete_selected_mapping` (after line 679, before `_draw_financial_chart`):

```python
    def refresh_review_view(self) -> None:
        pending = load_guidance_claims(status="pending_review")
        rows = [
            tuple(
                format_value(row.get(col))
                for col in ("claim_id", "ticker", "source_quarter", "target_period", "category", "product_or_segment", "direction", "quant_low", "quant_high")
            )
            for _, row in pending.iterrows()
        ]
        fill_tree(self.review_queue_tree, rows)
        self.review_selected_claim_id = None
        self.review_raw_text.configure(state="normal")
        self.review_raw_text.delete("1.0", "end")
        self.review_raw_text.configure(state="disabled")

    def _on_review_claim_selected(self, _event: object) -> None:
        selection = self.review_queue_tree.selection()
        if not selection:
            return
        values = self.review_queue_tree.item(selection[0], "values")
        if not values:
            return

        claim_id, _ticker, _source_quarter, _target_period, category, product_or_segment, direction, quant_low, quant_high = values
        self.review_selected_claim_id = claim_id

        pending = load_guidance_claims(status="pending_review")
        matches = pending[pending["claim_id"] == claim_id]
        raw_text = matches.iloc[0]["raw_text"] if not matches.empty else ""

        self.review_raw_text.configure(state="normal")
        self.review_raw_text.delete("1.0", "end")
        self.review_raw_text.insert("1.0", raw_text)
        self.review_raw_text.configure(state="disabled")

        self.review_category_var.set(category)
        self.review_direction_var.set(direction)
        self.review_product_var.set("" if product_or_segment == "-" else product_or_segment)
        self.review_quant_low_var.set("" if quant_low == "-" else quant_low)
        self.review_quant_high_var.set("" if quant_high == "-" else quant_high)

    def _save_review_edits(self) -> None:
        if not self.review_selected_claim_id:
            messagebox.showerror("Selection Error", "Select a pending claim first.")
            return

        def _optional_float(text: str) -> float | None:
            text = text.strip()
            return float(text) if text else None

        try:
            update_claim(
                self.review_selected_claim_id,
                category=self.review_category_var.get(),
                direction=self.review_direction_var.get(),
                product_or_segment=self.review_product_var.get().strip(),
                quant_low=_optional_float(self.review_quant_low_var.get()),
                quant_high=_optional_float(self.review_quant_high_var.get()),
            )
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Save Error", str(exc))
            return

        self.refresh_review_view()
        messagebox.showinfo("Saved", "Claim edits saved.")

    def _confirm_selected_claim(self) -> None:
        if not self.review_selected_claim_id:
            messagebox.showerror("Selection Error", "Select a pending claim first.")
            return
        try:
            confirm_claim(self.review_selected_claim_id, reviewed_by="analyst")
        except ValueError as exc:
            messagebox.showerror("Confirm Error", str(exc))
            return
        self.refresh_review_view()
        messagebox.showinfo("Confirmed", "Claim confirmed and queued for verification.")

    def _reject_selected_claim(self) -> None:
        if not self.review_selected_claim_id:
            messagebox.showerror("Selection Error", "Select a pending claim first.")
            return
        try:
            reject_claim(self.review_selected_claim_id, reviewed_by="analyst")
        except ValueError as exc:
            messagebox.showerror("Reject Error", str(exc))
            return
        self.refresh_review_view()
        messagebox.showinfo("Rejected", "Claim rejected.")
```

- [ ] **Step 5: Wire initial load**

In `__init__` (around line 80-92), add a call to populate the queue on startup, right after `self.refresh_management_view()`:

```python
            self.refresh_management_view()
            self.refresh_review_view()
```

- [ ] **Step 6: Manual verification**

Run: `cd chain_survey && python app/main.py`
Expected: app launches, "Guidance Review" tab appears between "Supply Chain Editor" and "Event Simulator", queue is empty (no claims yet — expected since none have been added through Task 4's script). Add a claim via a short Python shell using `core.guidance_service.add_claim` against the real `data/` dir, relaunch, confirm it shows up, and that Confirm/Reject/Save Edits work without raising.

- [ ] **Step 7: Commit**

```bash
cd chain_survey
git add app/gui_app.py
git commit -m "feat: add Guidance Review tab to desktop GUI

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: GUI — Guidance Tracker Sub-Tab (Company Explorer)

**Files:**
- Modify: `chain_survey/app/gui_app.py`

**Interfaces:**
- Consumes: `core.guidance_verification.compute_credibility_score` (Task 3), `core.guidance_service.load_guidance_claims` (Task 2), `core.data_loader.load_claim_outcomes` (Task 1), `self.company_tickers` (existing, built in `__init__` line 73).

This task also has no automated test — validated by manual run, consistent with Task 5 and the design spec's testing section.

- [ ] **Step 1: Add the import**

In `chain_survey/app/gui_app.py`, extend the guidance import added in Task 5 Step 1:

```python
from core.guidance_service import confirm_claim, load_guidance_claims, reject_claim, update_claim
from core.guidance_verification import compute_credibility_score
```

- [ ] **Step 2: Add the sub-tab**

In `_build_company_tab`, inside the `relation_notebook` block (around lines 234-265), add a new frame and tree:

```python
        upstream_frame = ttk.Frame(relation_notebook, padding=8)
        downstream_frame = ttk.Frame(relation_notebook, padding=8)
        product_view_frame = ttk.Frame(relation_notebook, padding=8)
        company_event_frame = ttk.Frame(relation_notebook, padding=8)
        chain_event_frame = ttk.Frame(relation_notebook, padding=8)
        guidance_tracker_frame = ttk.Frame(relation_notebook, padding=8)

        relation_notebook.add(upstream_frame, text="Upstream")
        relation_notebook.add(downstream_frame, text="Downstream")
        relation_notebook.add(product_view_frame, text="Products & Markets")
        relation_notebook.add(company_event_frame, text="Company Impact")
        relation_notebook.add(chain_event_frame, text="Chain Impact")
        relation_notebook.add(guidance_tracker_frame, text="Guidance Tracker")
```

Then, after the existing tree creation block (after line 265, before `_build_management_tab`), add:

```python
        score_row = ttk.Frame(guidance_tracker_frame)
        score_row.pack(fill="x", pady=(0, 8))
        ttk.Label(score_row, text="Guidance Credibility Score (trailing 8 quarters):", style="Subhead.TLabel").pack(side="left")
        self.guidance_score_label = ttk.Label(score_row, text="-")
        self.guidance_score_label.pack(side="left", padx=(8, 0))

        self.guidance_tracker_tree = self._create_tree(
            guidance_tracker_frame,
            ("source_quarter", "target_period", "category", "product_or_segment", "direction", "match_result", "note"),
        )
        self.guidance_tracker_tree.tag_configure("match_row", background="#d1fae5")
        self.guidance_tracker_tree.tag_configure("partial_row", background="#fef3c7")
        self.guidance_tracker_tree.tag_configure("miss_row", background="#fecaca")
        self.guidance_tracker_tree.tag_configure("pending_row", background="#e5e7eb")
```

- [ ] **Step 3: Add the refresh method**

Add after `refresh_company_view` (after line 533, before `_on_manage_company_change`):

```python
    def refresh_guidance_tracker(self, company_name: str) -> None:
        ticker = self.company_tickers.get(company_name)
        if not ticker:
            self.guidance_score_label.configure(text="-")
            fill_tree(self.guidance_tracker_tree, [])
            return

        score = compute_credibility_score(ticker)
        self.guidance_score_label.configure(text="-" if score is None else f"{score:.2f}")

        claims = load_guidance_claims()
        claims = claims[(claims["ticker"] == ticker) & (claims["status"] == "confirmed")] if not claims.empty else claims
        outcomes = data_loader.load_claim_outcomes()
        merged = claims.merge(outcomes, on="claim_id", how="left") if not claims.empty else claims

        row_tag_by_result = {
            "match": "match_row",
            "partial": "partial_row",
            "miss": "miss_row",
            "unverifiable": "pending_row",
        }

        clear_tree(self.guidance_tracker_tree)
        for _, row in merged.iterrows():
            match_result = row.get("match_result")
            tag = row_tag_by_result.get(match_result, "pending_row")
            values = tuple(
                format_value(row.get(col))
                for col in ("source_quarter", "target_period", "category", "product_or_segment", "direction", "match_result", "note")
            )
            self.guidance_tracker_tree.insert("", "end", values=values, tags=(tag,))
```

- [ ] **Step 4: Wire it into `refresh_company_view`**

At the end of `refresh_company_view` (right after `self._draw_financial_chart(financials, company_name)`, line 533), add:

```python
        self._draw_financial_chart(financials, company_name)
        self.refresh_guidance_tracker(company_name)
```

- [ ] **Step 5: Import `data_loader` directly**

Check the existing import on line 34:

```python
from core.data_loader import clear_data_caches, load_companies, load_edges, load_events, load_financials, load_products
```

`refresh_guidance_tracker` uses `data_loader.load_claim_outcomes()` (module-qualified), so add a bare module import alongside the existing `from core.data_loader import ...` line:

```python
from core import data_loader
from core.data_loader import clear_data_caches, load_companies, load_edges, load_events, load_financials, load_products
```

- [ ] **Step 6: Manual verification**

Run: `cd chain_survey && python app/main.py`
Expected: in Company Explorer, selecting a company shows a new "Guidance Tracker" sub-tab under "Upstream / Downstream Links" with a credibility score label (shows "-" until claims exist) and an empty/populated tree. After confirming a claim (Task 5) and running `core.guidance_verification.run_verification()` from a Python shell against the real `data/` dir, relaunch and confirm the row appears with the correct color tag.

- [ ] **Step 7: Commit**

```bash
cd chain_survey
git add app/gui_app.py
git commit -m "feat: add Guidance Tracker sub-tab to Company Explorer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Post-Implementation Checklist

- [ ] Run the full test suite: `cd chain_survey && python -m pytest tests/ -v` — all tests pass.
- [ ] Launch the app (`python app/main.py`) and walk through: add a claim via `guidance_service.add_claim` → confirm it in "Guidance Review" → run `guidance_verification.run_verification()` → see it reflected in "Guidance Tracker".
- [ ] Update `chain_survey/README.md`'s "Canonical Data Model" list to mention `source_documents.csv`, `guidance_claims.csv`, `claim_outcomes.csv`, following the existing bullet format.
