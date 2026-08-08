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
