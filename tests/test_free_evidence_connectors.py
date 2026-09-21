from __future__ import annotations

import json
import unittest

import pandas as pd

from core.free_evidence_connectors import (
    extract_data_gov_resource_url,
    parse_moea_export_orders_csv,
    parse_monthly_revenue_json,
    parse_tpca_listing,
)


class FreeEvidenceConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = pd.Timestamp("2026-09-21T02:40:00Z")

    def test_twse_monthly_revenue_parser(self) -> None:
        payload = json.dumps([{
            "出表日期":"1150910",
            "資料年月":"11508",
            "公司代號":"3037",
            "公司名稱":"欣興",
            "產業別":"電子零組件業",
            "營業收入-當月營收":"12345678",
            "營業收入-去年同月增減(%)":"25.5",
            "營業收入-上月比較增減(%)":"5.2"
        }], ensure_ascii=False)
        frame = parse_monthly_revenue_json(
            payload,
            source_id="twse_monthly_revenue",
            market="TWSE",
            collected_at=self.now,
            source_url="https://official.example/api",
        )
        self.assertEqual(frame.iloc[0]["ticker"], "3037")
        self.assertEqual(frame.iloc[0]["yoy_pct"], 25.5)
        self.assertEqual(frame.iloc[0]["published_at"], self.now)
        self.assertEqual(frame.iloc[0]["availability_policy"], "collection_time_conservative")

    def test_data_gov_metadata_url_discovery(self) -> None:
        metadata = {"distribution":[{"resourceDownloadUrl":"https://example.gov/data.csv"}]}
        self.assertEqual(extract_data_gov_resource_url(metadata), "https://example.gov/data.csv")

    def test_unicode_resource_url_encoding(self) -> None:
        import urllib.parse
        url = "https://example.gov/外銷訂單.csv"
        safe = urllib.parse.quote(url, safe=":/?&=%#")
        self.assertNotIn("外銷訂單", safe)
        self.assertIn("%E5%A4%96", safe)

    def test_moea_csv_parser(self) -> None:
        csv_text = "統計項目,資料期,統計值,計量單位\n資訊通信產品,115年7月,33269,百萬美元\n"
        frame = parse_moea_export_orders_csv(
            csv_text,
            source_id="moea_info",
            chain="Networking",
            dimension="orders_backlog",
            collected_at=self.now,
            source_url="https://data.gov.tw/example.csv",
        )
        self.assertEqual(frame.iloc[0]["raw_value"], 33269.0)
        self.assertEqual(frame.iloc[0]["chain"], "Networking")

    def test_tpca_public_text_parser(self) -> None:
        html = """
        <html><body>
        <a>2026年7月台灣硬板出口YoY26.91%</a>
        <a>2026年6月台灣上市櫃PCB原物料營收YoY 45.3%</a>
        <a>2026年6月台灣CCL 進口YoY 65.3%</a>
        </body></html>
        """
        frame = parse_tpca_listing(html, collected_at=self.now, source_url="https://tpca.example")
        self.assertEqual(set(frame["indicator"]), {"rigid_pcb_export_yoy","pcb_material_revenue_yoy","ccl_import_yoy"})
        self.assertEqual(len(frame), 3)


if __name__ == "__main__":
    unittest.main()
