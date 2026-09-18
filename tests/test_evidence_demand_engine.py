from __future__ import annotations

import unittest

import pandas as pd

from core.evidence_demand_engine import (
    deduplicate_evidence,
    freshness_weight,
    infer_demand_state,
    score_evidence,
)


class EvidenceDemandEngineTests(unittest.TestCase):
    @staticmethod
    def _evidence() -> pd.DataFrame:
        return pd.DataFrame(
            [
                ["e1", "AI Infrastructure", "buyer_commitment", "Cloud", "capex_a", "Hyperscaler capex", "2026-09-01", 0.8, "regulatory_filing", 0.95, 180],
                ["e2", "AI Infrastructure", "buyer_commitment", "Cloud", "capex_a", "Article repeats capex", "2026-09-02", 0.9, "anonymous_news", 0.30, 30],
                ["e3", "AI Infrastructure", "physical_throughput", "Compute", "gpu_ship", "GPU shipment", "2026-09-10", 0.7, "company_actual", 0.90, 90],
                ["e4", "AI Infrastructure", "physical_throughput", "HBM", "hbm_ship", "HBM shipment", "2026-09-10", 0.6, "company_actual", 0.90, 90],
                ["e5", "AI Infrastructure", "market_tightness", "Networking", "leadtime", "Lead time", "2026-09-08", 0.5, "channel_check", 0.50, 45],
                ["e6", "AI Infrastructure", "financial_confirmation", "Foundry", "revenue", "Foundry revenue", "2026-08-31", 0.4, "company_actual", 0.90, 120],
                ["e7", "AI Infrastructure", "orders_backlog", "Cooling", "cancel", "Order cancellation", "2026-09-11", -0.4, "supplier_commentary", 0.60, 60],
            ],
            columns=["evidence_id", "theme", "dimension", "chain", "evidence_group", "indicator", "as_of_date", "signal", "source_type", "reliability", "half_life_days"],
        )

    def test_freshness_halves_at_half_life(self) -> None:
        self.assertAlmostEqual(freshness_weight(90, 90), 0.5, places=6)

    def test_repeated_news_is_deduplicated(self) -> None:
        scored = score_evidence(self._evidence(), as_of_date="2026-09-12")
        deduped = deduplicate_evidence(scored)
        self.assertEqual(len(scored), 7)
        self.assertEqual(len(deduped), 6)
        capex = deduped[deduped["evidence_group"] == "capex_a"].iloc[0]
        self.assertEqual(capex["observation_count"], 2)
        self.assertGreater(capex["group_signal"], 0.7)

    def test_inference_rewards_independent_confirmation(self) -> None:
        result = infer_demand_state(self._evidence(), theme="AI Infrastructure", as_of_date="2026-09-12")
        self.assertGreater(result["score"], 55)
        self.assertGreaterEqual(result["independent_chains"], 5)
        self.assertGreaterEqual(result["positive_chains"], 4)
        self.assertGreater(len(result["conflicting_evidence"]), 0)

    def test_old_evidence_has_less_effect(self) -> None:
        frame = self._evidence()
        scored = score_evidence(frame, as_of_date="2026-12-10")
        recent = scored[scored["evidence_id"] == "e3"].iloc[0]
        self.assertLess(recent["freshness"], 0.6)

    def test_future_columns_do_not_affect_score(self) -> None:
        frame = self._evidence()
        frame["future_return"] = 999.0
        a = infer_demand_state(frame, as_of_date="2026-09-12")["score"]
        frame["future_return"] = -999.0
        b = infer_demand_state(frame, as_of_date="2026-09-12")["score"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
