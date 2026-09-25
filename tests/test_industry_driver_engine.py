from __future__ import annotations

import unittest

import pandas as pd

from core.industry_driver_engine import (
    evaluate_all_industry_models,
    evaluate_industry_model,
    load_industry_models,
    load_validated_driver_registry,
    map_models_to_companies,
)


class IndustryDriverEngineTests(unittest.TestCase):
    @staticmethod
    def _evidence() -> pd.DataFrame:
        return pd.DataFrame(
            [
                ["e1","AI Infrastructure","buyer_commitment","Cloud","cloud_capex","Cloud capex","2026-09-01",0.8,"regulatory_filing",0.95,180],
                ["e2","AI Infrastructure","physical_throughput","Compute","gpu_ship","GPU shipment","2026-09-10",0.7,"company_actual",0.90,90],
                ["e3","AI Infrastructure","physical_throughput","HBM","hbm_ship","HBM shipment","2026-09-10",0.6,"company_actual",0.90,90],
                ["e4","AI Infrastructure","physical_throughput","Networking","net_ship","Network shipment","2026-09-09",0.5,"company_actual",0.85,90],
                ["e5","AI Infrastructure","market_tightness","ABF","abf_tight","ABF tightness","2026-09-08",0.55,"channel_check",0.55,60],
                ["e6","AI Infrastructure","market_tightness","Foundry","foundry_util","Foundry utilization","2026-09-08",0.45,"company_actual",0.85,90],
                ["e7","AI Infrastructure","financial_confirmation","Foundry","foundry_rev","Foundry revenue","2026-08-31",0.4,"company_actual",0.90,120],
            ],
            columns=["evidence_id","theme","dimension","chain","evidence_group","indicator","as_of_date","signal","source_type","reliability","half_life_days"],
        )

    def test_four_models_load(self) -> None:
        models = load_industry_models()
        self.assertEqual(set(models), {
            "ic_substrate_abf_bt",
            "memory_dram_hbm_nand",
            "foundry_advanced_node",
            "ccl_pcb_high_speed",
        })

    def test_only_validated_registry_entries_are_loaded(self) -> None:
        registry = load_validated_driver_registry()
        self.assertIn("tpca_pcb_revenue_yoy_to_abf_revenue_1m", registry)
        self.assertEqual(registry["tpca_pcb_revenue_yoy_to_abf_revenue_1m"]["status"], "VALIDATED")

    def test_abf_model_translates_evidence_into_product_economics(self) -> None:
        result = evaluate_industry_model(self._evidence(), "ic_substrate_abf_bt", as_of_date="2026-09-12")
        self.assertGreater(result["score"], 50)
        self.assertGreater(result["product_economics"]["volume_score"], 50)
        self.assertGreater(result["product_economics"]["asp_score"], 50)
        self.assertGreater(result["coverage"], 50)
        self.assertIn("Revenue = shipment volume", result["equations"]["revenue_equation"])
        end_demand = result["drivers"][result["drivers"]["driver_id"] == "end_demand"].iloc[0]
        self.assertEqual(end_demand["evidence_status"], "EMPIRICALLY_LINKED")
        self.assertEqual(int(end_demand["empirical_best_lag_months"]), 1)
        self.assertAlmostEqual(float(end_demand["empirical_spearman"]), 0.5800988032303457)
        self.assertEqual(len(result["validated_relations"]), 1)

    def test_all_models_return_rankable_table(self) -> None:
        table = evaluate_all_industry_models(self._evidence(), as_of_date="2026-09-12")
        self.assertEqual(len(table), 4)
        self.assertTrue(table["score"].between(0, 100).all())
        self.assertTrue(table["confidence"].between(0, 100).all())

    def test_company_mapping_uses_product_exposure(self) -> None:
        results = evaluate_all_industry_models(self._evidence(), as_of_date="2026-09-12")
        rel = pd.DataFrame([
            {"company":"南電","relation":"produces","product":"ABF Substrate","weight":0.85},
            {"company":"台積電","relation":"produces","product":"3nm/4nm Wafer","weight":1.0},
        ])
        mapped = map_models_to_companies(results, rel)
        self.assertEqual(set(mapped["company"]), {"南電", "台積電"})
        nan = mapped[mapped["company"] == "南電"].iloc[0]
        self.assertAlmostEqual(nan["exposure_weight"], 0.85)

    def test_future_columns_cannot_change_industry_score(self) -> None:
        evidence = self._evidence()
        a = evaluate_industry_model(evidence.assign(future_return=999), "foundry_advanced_node", as_of_date="2026-09-12")["score"]
        b = evaluate_industry_model(evidence.assign(future_return=-999), "foundry_advanced_node", as_of_date="2026-09-12")["score"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
