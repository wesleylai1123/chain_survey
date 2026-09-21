from __future__ import annotations

import unittest

import pandas as pd

from scripts.build_real_point_in_time_evidence import build_real_evidence, normalize_yoy_to_signal


class RealPointInTimeEvidenceTests(unittest.TestCase):
    def test_signal_transform_is_reproducible(self) -> None:
        self.assertEqual(normalize_yoy_to_signal(53.3), 0.533)
        self.assertEqual(normalize_yoy_to_signal(250), 1.0)
        self.assertEqual(normalize_yoy_to_signal(-130), -1.0)

    def test_published_at_becomes_as_of_date(self) -> None:
        raw = pd.DataFrame([{
            "evidence_id":"x","theme":"AI Infrastructure","dimension":"orders_backlog",
            "chain":"Compute","evidence_group":"g","indicator":"orders",
            "period_date":"2026-07-31","published_at":"2026-08-20T16:00:00+08:00",
            "raw_value":100,"raw_unit":"USD million","yoy_pct":20,
            "source_type":"government_statistic","reliability":0.98,"half_life_days":90,
            "source":"https://example.com","notes":""
        }])
        built = build_real_evidence(raw)
        self.assertEqual(built.iloc[0]["signal"], 0.2)
        self.assertEqual(built.iloc[0]["provenance"], "REAL_POINT_IN_TIME")
        self.assertEqual(built.iloc[0]["as_of_date"], built.iloc[0]["published_at"])

    def test_future_period_cannot_leak_before_publication(self) -> None:
        raw = pd.DataFrame([{
            "evidence_id":"x","theme":"AI Infrastructure","dimension":"financial_confirmation",
            "chain":"Foundry","evidence_group":"g","indicator":"revenue",
            "period_date":"2026-08-31","published_at":"2026-09-10",
            "raw_value":100,"raw_unit":"TWD million","yoy_pct":50,
            "source_type":"company_actual","reliability":0.95,"half_life_days":120,
            "source":"https://example.com","notes":""
        }])
        built = build_real_evidence(raw)
        available = built[built["as_of_date"] <= pd.Timestamp("2026-09-09", tz="UTC")]
        self.assertTrue(available.empty)


if __name__ == "__main__":
    unittest.main()
