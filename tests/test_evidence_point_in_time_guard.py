from __future__ import annotations

import unittest

import pandas as pd

from core.evidence_demand_engine import score_evidence


class EvidencePointInTimeGuardTests(unittest.TestCase):
    def test_future_publication_is_excluded(self) -> None:
        evidence = pd.DataFrame([
            {
                "evidence_id":"known",
                "theme":"AI Infrastructure",
                "dimension":"orders_backlog",
                "chain":"Compute",
                "evidence_group":"known",
                "indicator":"known order",
                "as_of_date":"2026-08-20T16:00:00+08:00",
                "signal":0.5,
                "source_type":"government_statistic",
            },
            {
                "evidence_id":"future",
                "theme":"AI Infrastructure",
                "dimension":"financial_confirmation",
                "chain":"Foundry",
                "evidence_group":"future",
                "indicator":"future revenue",
                "as_of_date":"2026-09-10",
                "signal":0.9,
                "source_type":"company_actual",
            },
        ])
        scored = score_evidence(evidence, as_of_date="2026-09-01")
        self.assertEqual(list(scored["evidence_id"]), ["known"])

    def test_no_evidence_before_first_publication(self) -> None:
        evidence = pd.DataFrame([{
            "evidence_id":"future",
            "theme":"AI Infrastructure",
            "dimension":"financial_confirmation",
            "chain":"Foundry",
            "evidence_group":"future",
            "indicator":"future revenue",
            "as_of_date":"2026-09-10",
            "signal":0.9,
            "source_type":"company_actual",
        }])
        scored = score_evidence(evidence, as_of_date="2026-09-01")
        self.assertTrue(scored.empty)


if __name__ == "__main__":
    unittest.main()
