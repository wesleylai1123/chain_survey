from __future__ import annotations

import unittest
from io import StringIO

import scripts.collect_trendforce_public_history as mod


class TrendforcePublicHistoryTests(unittest.TestCase):
    def test_parse_public_price_table(self) -> None:
        mod.StringIO = StringIO
        html = """
        <div>Last Update 2026-09-21 11:00 (GMT+8)</div>
        <div>Last Update 2026-07-31 15:00 (GMT+8)</div>
        <table>
          <tr><th>Item</th><th>Session Average</th><th>Session Change</th></tr>
          <tr><td>DDR5 16Gb (2Gx8) 4800/5600</td><td>8.2</td><td>+0.75%</td></tr>
        </table>
        <table>
          <tr><th>Item</th><th>Average</th><th>Change</th></tr>
          <tr><td>DDR5 8GB SO-DIMM</td><td>30.0</td><td>+13.04%</td></tr>
          <tr><td>DDR4 16GB SO-DIMM</td><td>40.0</td><td>+16.74%</td></tr>
        </table>
        """
        out = mod.parse_public_page(html)
        self.assertEqual(len(out), 3)
        self.assertIn("dram_spot_ddr5_16gb", set(out["metric_id"]))
        self.assertIn("dram_contract_ddr5_8gb_sodimm", set(out["metric_id"]))
        self.assertTrue(out["change_pct"].notna().all())

    def test_append_history_is_idempotent(self) -> None:
        import pandas as pd, tempfile
        from pathlib import Path
        current = pd.DataFrame([{
            "metric_id":"x","kind":"spot","product":"x","observed_at":"2026-09-21T11:00:00+08:00",
            "published_at":"2026-09-21T11:00:00+08:00","session_average":1.0,"change_pct":0.5,
            "source_url":"u","source":"s","knowledge_time_method":"page_last_update"
        }])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"h.csv"
            a=mod.append_history(current,path)
            a.to_csv(path,index=False)
            b=mod.append_history(current,path)
            self.assertEqual(len(b),1)


if __name__ == "__main__":
    unittest.main()
