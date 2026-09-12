import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.full_universe_cache import CacheManifest, merge_cached_frame


class FullUniverseCacheTests(unittest.TestCase):
    def test_cache_hit_and_incremental_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = CacheManifest(Path(tmp) / "manifest.json")
            manifest.mark_success("2330", "prices", "2020-01-01", "2026-09-01", 100)
            self.assertIsNone(manifest.pending_range("2330", "prices", "2020-01-01", "2026-08-31"))
            self.assertEqual(manifest.pending_range("2330", "prices", "2020-01-01", "2026-09-10"), ("2026-09-02", "2026-09-10"))

    def test_failed_entry_retries_full_requested_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = CacheManifest(Path(tmp) / "manifest.json")
            manifest.mark_failed("2330", "prices", "2020-01-01", "2026-09-10", "boom")
            self.assertEqual(manifest.pending_range("2330", "prices", "2020-01-01", "2026-09-10"), ("2020-01-01", "2026-09-10"))

    def test_merge_cached_frame_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            pd.DataFrame([
                {"date": "2026-09-01", "stock_id": "2330", "close": 100},
                {"date": "2026-09-02", "stock_id": "2330", "close": 101},
            ]).to_csv(path, index=False)
            merged = merge_cached_frame(path, pd.DataFrame([
                {"date": "2026-09-02", "stock_id": "2330", "close": 102},
                {"date": "2026-09-03", "stock_id": "2330", "close": 103},
            ]))
            self.assertEqual(len(merged), 3)
            self.assertEqual(float(merged.loc[merged["date"] == "2026-09-02", "close"].iloc[0]), 102.0)


if __name__ == "__main__":
    unittest.main()
