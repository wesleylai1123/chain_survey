from __future__ import annotations

import unittest

from scripts.backfill_mops_abf_history import parse_mops_month


class MopsHistoryParserTests(unittest.TestCase):
    def test_parse_target_companies(self) -> None:
        html = """
        <table>
          <tr><th>公司代號</th><th>公司名稱</th><th>當月營收</th><th>去年同月增減(%)</th></tr>
          <tr><td>3037</td><td>欣興</td><td>11,600,477</td><td>16.18</td></tr>
          <tr><td>3189</td><td>景碩</td><td>3,204,487</td><td>10.00</td></tr>
          <tr><td>8046</td><td>南電</td><td>3,166,126</td><td>12.84</td></tr>
          <tr><td>9999</td><td>Other</td><td>1</td><td>1</td></tr>
        </table>
        """
        out = parse_mops_month(html, 2026, 2)
        self.assertEqual(set(out["ticker"]), {"3037.TW","3189.TW","8046.TW"})
        self.assertTrue((out["knowledge_time_method"] == "regulatory_deadline_proxy").all())
        self.assertTrue((out["published_at"] > out["period_date"]).all())


if __name__ == "__main__":
    unittest.main()
