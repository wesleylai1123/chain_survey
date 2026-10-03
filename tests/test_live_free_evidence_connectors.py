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
from scripts.collect_free_evidence import (
    moea_snapshot_to_evidence,
    parse_month_period,
    revenue_snapshot_to_evidence,
)


class LiveFreeEvidenceConnectorTests(unittest.TestCase):
    def setUp(self):
        self.now=pd.Timestamp("2026-09-21T02:40:00Z")

    def test_twse_monthly_revenue_parser_is_forward_collected(self):
        payload=json.dumps([{
            "資料年月":"11508","公司代號":"3037","公司名稱":"欣興","產業別":"電子零組件業",
            "營業收入-當月營收":"12345678","營業收入-去年同月增減(%)":"25.5","營業收入-上月比較增減(%)":"5.2"
        }],ensure_ascii=False)
        frame=parse_monthly_revenue_json(payload,source_id="twse_monthly_revenue",market="TWSE",collected_at=self.now,source_url="https://official.example/api")
        self.assertEqual(frame.iloc[0]["ticker"],"3037")
        self.assertEqual(frame.iloc[0]["published_at"],self.now)
        self.assertEqual(frame.iloc[0]["availability_policy"],"collection_time_conservative")

    def test_data_gov_metadata_url_discovery(self):
        metadata={"distribution":[{"resourceDownloadUrl":"https://example.gov/data.csv"}]}
        self.assertEqual(extract_data_gov_resource_url(metadata),"https://example.gov/data.csv")

    def test_moea_csv_and_yoy(self):
        csv_text="統計項目,資料期,統計值,計量單位\n資訊通信產品,114年7月,100,百萬美元\n資訊通信產品,115年7月,150,百萬美元\n"
        frame=parse_moea_export_orders_csv(csv_text,source_id="moea_info",chain="Networking",dimension="orders_backlog",collected_at=self.now,source_url="https://data.gov.tw/example.csv")
        evidence=moea_snapshot_to_evidence(frame)
        self.assertEqual(len(evidence),1)
        self.assertAlmostEqual(evidence.iloc[0]["yoy_pct"],50.0)
        self.assertEqual(evidence.iloc[0]["reliability_basis"],"SOURCE_CLASS_PRIOR")

    def test_tpca_public_text_parser(self):
        html="<a>2026年7月台灣硬板出口YoY26.91%</a><a>2026年6月台灣上市櫃PCB原物料營收YoY 45.3%</a><a>2026年6月台灣CCL 進口YoY 65.3%</a>"
        frame=parse_tpca_listing(html,collected_at=self.now,source_url="https://tpca.example")
        self.assertEqual(set(frame["indicator"]),{"rigid_pcb_export_yoy","pcb_material_revenue_yoy","ccl_import_yoy"})

    def test_revenue_mapping_labels_exposure_assumption(self):
        frame=pd.DataFrame([{
            "source_id":"twse_monthly_revenue","ticker":"3037","company":"欣興","period":"11508",
            "yoy_pct":30.0,"published_at":self.now,"source":"official"
        }])
        rel=pd.DataFrame([{"company":"欣興","product":"ABF Substrate","weight":0.9}])
        evidence=revenue_snapshot_to_evidence(frame,rel)
        self.assertEqual(evidence.iloc[0]["chain"],"ABF")
        self.assertEqual(evidence.iloc[0]["exposure_basis"],"CONFIGURED_ASSUMPTION")
        self.assertEqual(evidence.iloc[0]["reliability_basis"],"SOURCE_CLASS_PRIOR")

    def test_roc_month_period(self):
        self.assertEqual(parse_month_period("115年7月"),pd.Timestamp("2026-07-01"))
        self.assertEqual(parse_month_period("11507"),pd.Timestamp("2026-07-01"))


if __name__=="__main__":
    unittest.main()
