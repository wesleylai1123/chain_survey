from __future__ import annotations

import unittest

from scripts.backfill_tpca_history import parse_list_page


class TpcaHistoryParserTests(unittest.TestCase):
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
