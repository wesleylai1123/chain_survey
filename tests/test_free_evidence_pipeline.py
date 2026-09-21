from __future__ import annotations

import unittest

import pandas as pd

from scripts.collect_free_evidence import (
    moea_snapshot_to_evidence,
    parse_month_period,
    revenue_snapshot_to_evidence,
)


class FreeEvidencePipelineTests(unittest.TestCase):
    def test_roc_month_period(self) -> None:
        self.assertEqual(parse_month_period("115年7月"), pd.Timestamp("2026-07-01"))
        self.assertEqual(parse_month_period("11507"), pd.Timestamp("2026-07-01"))
        self.assertEqual(parse_month_period("2026-07"), pd.Timestamp("2026-07-01"))

    def test_company_revenue_maps_to_product_chain(self) -> None:
        now = pd.Timestamp("2026-09-21T03:00:00Z")
        frame = pd.DataFrame([{
            "source_id":"twse_monthly_revenue","ticker":"3037","company":"欣興","industry":"電子零組件業",
            "period":"11508","raw_value":100,"raw_unit":"TWD thousand","yoy_pct":30.0,"mom_pct":5.0,
            "published_at":now,"collected_at":now,"source":"official","availability_policy":"collection_time_conservative",
            "provenance":"LIVE_OFFICIAL_SNAPSHOT",
        }])
        rel = pd.DataFrame([{"company":"欣興","product":"ABF Substrate","weight":0.9}])
        evidence = revenue_snapshot_to_evidence(frame, rel)
        self.assertEqual(evidence.iloc[0]["chain"], "ABF")
        self.assertAlmostEqual(evidence.iloc[0]["signal"], 0.30)
        self.assertEqual(evidence.iloc[0]["provenance"], "LIVE_FREE_POINT_IN_TIME")

    def test_moea_yoy_is_derived_from_official_levels(self) -> None:
        now = pd.Timestamp("2026-09-21T03:00:00Z")
        frame = pd.DataFrame([
            {"source_id":"moea_info","period":"114年7月","indicator":"資訊通信產品","chain":"Networking","dimension":"orders_backlog","raw_value":100.0,"published_at":now,"source":"official"},
            {"source_id":"moea_info","period":"115年7月","indicator":"資訊通信產品","chain":"Networking","dimension":"orders_backlog","raw_value":150.0,"published_at":now,"source":"official"},
        ])
        evidence = moea_snapshot_to_evidence(frame)
        self.assertEqual(len(evidence), 1)
        self.assertAlmostEqual(evidence.iloc[0]["yoy_pct"], 50.0)
        self.assertAlmostEqual(evidence.iloc[0]["signal"], 0.5)


if __name__ == "__main__":
    unittest.main()
