from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from scripts.extract_abf_operating_candidates import extract_candidates_from_pages, fetch_pdf_conditional


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

    def test_conditional_fetch_reuses_cache_only_after_http_304(self):
        class Response:
            def __init__(self,body,headers):
                self._body=body
                self.headers=headers
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return self._body

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            calls=[]
            def fake_urlopen(req,timeout=25):
                calls.append(dict(req.header_items()))
                if len(calls)==1:
                    return Response(b"%PDF-stable",{"ETag":"\"abc\"","Last-Modified":"Wed, 01 Oct 2026 00:00:00 GMT"})
                raise HTTPError(req.full_url,304,"Not Modified",hdrs={},fp=None)

            with patch("scripts.extract_abf_operating_candidates.urlopen",side_effect=fake_urlopen):
                first=fetch_pdf_conditional("https://example.com/report.pdf",stock_id="8046",raw_root=root,retries=1)
                second=fetch_pdf_conditional("https://example.com/report.pdf",stock_id="8046",raw_root=root,retries=1)

            self.assertEqual(first.fetch_mode,"FULL_GET")
            self.assertTrue(first.changed)
            self.assertEqual(second.fetch_mode,"HTTP_304_CACHE")
            self.assertFalse(second.changed)
            self.assertEqual(first.sha256,second.sha256)
            second_headers={k.lower():v for k,v in calls[1].items()}
            self.assertEqual(second_headers.get("if-none-match"),"\"abc\"")
            self.assertIn("if-modified-since",second_headers)
            self.assertTrue((root/"manifest.json").exists())

    def test_network_error_never_silently_reuses_cached_pdf(self):
        class Response:
            headers={"ETag":"\"abc\""}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return b"%PDF-stable"

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch("scripts.extract_abf_operating_candidates.urlopen",return_value=Response()):
                fetch_pdf_conditional("https://example.com/report.pdf",stock_id="8046",raw_root=root,retries=1)
            with patch("scripts.extract_abf_operating_candidates.urlopen",side_effect=URLError("offline")):
                with self.assertRaises(RuntimeError):
                    fetch_pdf_conditional("https://example.com/report.pdf",stock_id="8046",raw_root=root,retries=1)


if __name__=="__main__":
    unittest.main()
