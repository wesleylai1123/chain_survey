from __future__ import annotations

import unittest
import pandas as pd

from scripts.build_free_industry_evidence import (
    _signal,
    build_mops_company_evidence,
    build_snapshot_evidence,
)


class FreeIndustryEvidenceTests(unittest.TestCase):
    def test_transforms_are_explicit_and_bounded(self) -> None:
        self.assertAlmostEqual(_signal(45.3, "pct_yoy"), 0.453)
        self.assertAlmostEqual(_signal(13.04, "pct_change_ref20"), 0.652)
        self.assertAlmostEqual(_signal(0.75, "pct_change_ref5"), 0.15)
        self.assertEqual(_signal(500, "pct_yoy"), 1.0)

    def test_mops_publication_date_is_after_period_end(self) -> None:
        frame = pd.DataFrame([{
            "company":"南電","ticker":"8046.TW","period":11502,
            "monthly_revenue":3166126,"yoy_pct":12.84,
            "source_date":1150317,"source":"TWSE/MOPS official open data",
        }])
        out = build_mops_company_evidence(frame)
        self.assertEqual(out.iloc[0]["chain"], "ABF")
        self.assertGreater(out.iloc[0]["published_at"], out.iloc[0]["period_date"])

    def test_snapshot_keeps_publication_timestamp(self) -> None:
        frame = pd.DataFrame([{
            "source_id":"tpca","evidence_id":"x","theme":"AI Infrastructure",
            "dimension":"physical_throughput","chain":"CCL","evidence_group":"g",
            "indicator":"CCL export","period_date":"2026-06-30",
            "published_at":"2026-07-22T00:00:00+08:00","raw_value":27.4,
            "raw_unit":"percent","change_pct":27.4,"transform_type":"pct_yoy",
            "source_type":"industry_association","reliability":0.85,
            "half_life_days":90,"source":"https://example.com","notes":""
        }])
        out = build_snapshot_evidence(frame)
        self.assertEqual(out.iloc[0]["provenance"], "REAL_POINT_IN_TIME_FREE")
        self.assertEqual(out.iloc[0]["signal"], 0.274)


if __name__ == "__main__":
    unittest.main()
