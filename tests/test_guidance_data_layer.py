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

    def test_loaders_preserve_numeric_only_ids_as_text(self) -> None:
        doc_id = "000123456789"
        claim_id = "000234567890"
        (self.data_dir / "source_documents.csv").write_text(
            "doc_id,ticker,file_path,source_quarter,call_date\n"
            f"{doc_id},2330.TW,transcript.pdf,114Q2,2025-07-18\n",
            encoding="utf-8",
        )
        (self.data_dir / "guidance_claims.csv").write_text(
            "claim_id,doc_id,ticker,source_quarter,target_period,category,product_or_segment,"
            "direction,quant_low,quant_high,raw_text,status,reviewed_by,reviewed_at\n"
            f"{claim_id},{doc_id},2330.TW,114Q2,114Q3,revenue_growth,,up,10,15,rev up,confirmed,,\n",
            encoding="utf-8",
        )
        (self.data_dir / "claim_outcomes.csv").write_text(
            "claim_id,actual_value,match_result,evaluated_at,note\n"
            f"{claim_id},12,match,2025-10-18,direction matched\n",
            encoding="utf-8",
        )

        documents = data_loader.load_source_documents()
        claims = data_loader.load_guidance_claims()
        outcomes = data_loader.load_claim_outcomes()
        for column, actual, expected in (
            ("source_documents.doc_id", documents.loc[0, "doc_id"], doc_id),
            ("guidance_claims.doc_id", claims.loc[0, "doc_id"], doc_id),
            ("guidance_claims.claim_id", claims.loc[0, "claim_id"], claim_id),
            ("claim_outcomes.claim_id", outcomes.loc[0, "claim_id"], claim_id),
        ):
            with self.subTest(column=column):
                self.assertEqual(actual, expected)

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
