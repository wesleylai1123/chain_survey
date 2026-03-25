from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.data_loader import load_event_templates, load_macro_exposures, load_macro_factors
from core.impact_engine import simulate_event


class MacroDominoAnalysisTests(unittest.TestCase):
    def test_macro_datasets_load(self) -> None:
        factors = load_macro_factors()
        exposures = load_macro_exposures()

        self.assertIn("factor_id", factors.columns)
        self.assertIn("entity_name", exposures.columns)
        self.assertGreaterEqual(len(factors), 3)
        self.assertGreaterEqual(len(exposures), 10)

    def test_event_templates_include_macro_scenarios(self) -> None:
        events = load_event_templates()
        macro_events = [event for event in events if event.get("macro_seed_rules")]

        self.assertGreaterEqual(len(macro_events), 3)
        self.assertTrue(any(event["event_id"] == "global_handset_demand_slowdown" for event in macro_events))

    def test_macro_scenario_generates_explainable_impacts(self) -> None:
        result = simulate_event("全球智慧手機需求轉弱")

        self.assertFalse(result.empty)
        self.assertIn("macro_factor", result.columns)
        self.assertIn("seed_source", result.columns)
        self.assertTrue((result["seed_source"] == "macro_exposure").any())
        self.assertTrue((result["macro_factor"] == "全球智慧手機需求").any())
        self.assertTrue(result["path"].str.contains("macro_seed").any())
        self.assertTrue((result["company"] == "小米").any())


if __name__ == "__main__":
    unittest.main()
