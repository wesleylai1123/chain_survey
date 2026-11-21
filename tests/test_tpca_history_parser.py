from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
import pandas as pd

from scripts.backfill_tpca_history import parse_list_page


class TpcaHistoryParserTests(unittest.TestCase):
    def test_partial_listing_refresh_preserves_verified_history_and_pit(self):
        from scripts import backfill_tpca_history as module
        self.assertTrue(hasattr(module,'merge_history'),'history merge is missing')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tpca.csv'
            old=pd.DataFrame([{'metric_id':'pcb_revenue_yoy','period':'2024-01','change_pct':2,
                'published_at':'2024-02-15T23:59:59+08:00','source_url':'https://example.com/old'}])
            old.to_csv(path,index=False)
            current=pd.DataFrame([{'metric_id':'pcb_revenue_yoy','period':'2026-09','change_pct':10,
                'published_at':'2026-10-15T23:59:59+08:00','source_url':'https://example.com/new'}])
            merged=module.merge_history(current,path)
            self.assertEqual(len(merged),2)
            retained=merged[merged.period.eq('2024-01')].iloc[0]
            self.assertEqual(retained.published_at,old.iloc[0].published_at)
            self.assertEqual(retained.source_url,old.iloc[0].source_url)
            merged.to_csv(path,index=False)
            pd.testing.assert_frame_equal(module.merge_history(current,path),merged)
            revised=current.copy()
            revised['change_pct']=11
            result=module.merge_history(revised,path)
            self.assertEqual(float(result[result.period.eq('2026-09')].iloc[0].change_pct),11)

    def test_parse_public_titles(self) -> None:
        html = """
        <ul>
          <li>2026-07-15 <a href="news_detail.php?news_no=1">2026年6月 PCB上市櫃營收 YoY 32.08%</a></li>
          <li>2026-07-22 <a href="news_detail.php?news_no=2">2026年6月 PCB原物料營收 YoY 45.3%</a></li>
          <li>2026-07-22 <a href="news_detail.php?news_no=3">2026年6月 CCL 進口 YoY 65.3%</a></li>
          <li>2026-07-22 <a href="news_detail.php?news_no=4">2026年6月 CCL 出口 YoY 27.4%</a></li>
        </ul>
        """
        rows = parse_list_page(html, 2025)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["metric_id"] for r in rows}, {
            "pcb_revenue_yoy","pcb_material_revenue_yoy","ccl_import_yoy","ccl_export_yoy"
        })
        self.assertTrue(all(r["published_at"].startswith("2026-07-") for r in rows))


if __name__ == "__main__":
    unittest.main()
