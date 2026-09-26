from __future__ import annotations

import unittest

from core.indicator_taxonomy import classify_indicator, indicator_table, load_indicator_catalog


class IndicatorTaxonomyTests(unittest.TestCase):
    def test_catalog_requires_relative_target(self) -> None:
        payload=load_indicator_catalog()
        self.assertGreaterEqual(len(payload["indicators"]),6)
        self.assertTrue(all(x["relative_to"] for x in payload["indicators"]))

    def test_validated_pcb_indicator_is_leading_relative_to_abf_revenue(self) -> None:
        item=classify_indicator("tpca_pcb_revenue_yoy")
        self.assertEqual(item["timing_class"],"LEADING")
        self.assertEqual(item["lead_lag"]["value"],1)
        self.assertEqual(item["evidence_status"],"VALIDATED")

    def test_financial_confirmation_is_lagging_not_fake_validated(self) -> None:
        eps=classify_indicator("eps")
        self.assertEqual(eps["timing_class"],"LAGGING")
        self.assertEqual(eps["evidence_status"],"CAUSAL_HYPOTHESIS")
        self.assertIsNone(eps["lead_lag"]["value"])

    def test_table_contains_all_three_timing_classes(self) -> None:
        table=indicator_table()
        self.assertEqual(set(table["timing_class"]),{"LEADING","COINCIDENT","LAGGING"})


if __name__=="__main__":
    unittest.main()
