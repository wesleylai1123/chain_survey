from __future__ import annotations

import unittest

from scripts.extract_abf_operating_candidates import extract_candidates_from_pages


class AbfOperatingCandidateTests(unittest.TestCase):
    def test_extracts_utilization_range_product_mix_and_downside(self):
        pages=[
            "ABF utilization rate was 75-80%. ABF product mix was 68%. "
            "Management noted inventory correction and order cuts at customers.",
            "New ABF capacity expansion will start ramping next quarter. "
            "Demand outlook remains strong and price hike discussions continue.",
        ]
        out=extract_candidates_from_pages("3037","Unimicron","test","https://example.com/q4.pdf",pages,"abc")
        kinds=set(out["signal_type"])
        self.assertIn("UTILIZATION_RANGE",kinds)
        self.assertIn("ABF_MIX",kinds)
        self.assertIn("INVENTORY_CORRECTION",kinds)
        self.assertIn("ORDER_CUT",kinds)
        self.assertIn("CAPACITY_EXPANSION",kinds)
        self.assertIn("GUIDANCE_UP",kinds)
        self.assertIn("PRICE_UP",kinds)
        row=out[out["signal_type"]=="UTILIZATION_RANGE"].iloc[0]
        self.assertEqual(float(row["value_low"]),75.0)
        self.assertEqual(float(row["value_high"]),80.0)
        self.assertEqual(row["review_status"],"CANDIDATE")

    def test_preserves_full_utilization_as_qualitative_event(self):
        out=extract_candidates_from_pages(
            "8046","Nan Ya PCB","test","https://example.com/q1.pdf",
            ["The new ABF line reached full utilization in Q1."],"abc",
        )
        row=out[out["signal_type"]=="FULL_UTILIZATION"].iloc[0]
        self.assertEqual(row["unit"],"event")
        self.assertEqual(row["direction"],"UP")
        self.assertTrue(str(row["value"])=="<NA>" or str(row["value"])=="nan")

    def test_does_not_promote_candidates_to_validated_observations(self):
        out=extract_candidates_from_pages(
            "3189","Kinsus","test","https://example.com/q2.pdf",
            ["ABF utilization 82%."],"abc",
        )
        self.assertEqual(set(out["review_status"]),{"CANDIDATE"})

    def test_source_permission_blocks_esg_guidance_false_positive(self):
        out=extract_candidates_from_pages(
            "3189","Kinsus","kinsus_esg","https://example.com/esg.pdf",
            ["展望未來需求強勁，產能需求增加。"],"abc",
            use_for="capacity_proxy;production_proxy;resource_intensity",
        )
        self.assertTrue(out.empty)

    def test_abf_metric_requires_abf_context(self):
        out=extract_candidates_from_pages(
            "3189","Kinsus","kinsus_ir","https://example.com/ir.pdf",
            ["Overall company utilization was 82%."],"abc",
            use_for="guidance;utilization;product_mix;capacity;downside",
        )
        self.assertTrue(out.empty)


if __name__=="__main__":
    unittest.main()
