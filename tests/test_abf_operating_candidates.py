from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from scripts.extract_abf_operating_candidates import _safe_url, extract_candidates_from_pages, fetch_pdf_conditional


class AbfOperatingCandidateTests(unittest.TestCase):
    def test_encoded_document_url_is_not_encoded_twice(self):
        url="https://www.kinsus.com.tw/upload/media/ir/Investor/1150310%E6%B3%95%E8%AA%AA%E6%9C%83.pdf"
        self.assertEqual(_safe_url(url),url)

    def test_document_url_encodes_unicode_and_preserves_existing_escapes(self):
        self.assertEqual(
            _safe_url("https://example.com/法說 report%2Fv1%25.pdf?download=1#page=2"),
            "https://example.com/%E6%B3%95%E8%AA%AA%20report%2Fv1%25.pdf?download=1#page=2",
        )

    def test_corrupted_cache_is_refetched_and_repaired(self):
        class Response:
            headers={"ETag":"\"abc\""}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return b"%PDF-stable"

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            url="https://example.com/report.pdf"
            with patch("scripts.extract_abf_operating_candidates.urlopen",return_value=Response()):
                first=fetch_pdf_conditional(url,stock_id="8046",raw_root=root,retries=1)
            cached_path=Path(first.raw_path)
            cached_path.write_bytes(b"corrupted")
            calls=[]
            def fake_urlopen(req,timeout=25):
                headers={k.lower():v for k,v in req.header_items()}
                calls.append(headers)
                if "if-none-match" in headers:
                    raise HTTPError(req.full_url,304,"Not Modified",hdrs={},fp=None)
                return Response()
            with patch("scripts.extract_abf_operating_candidates.urlopen",side_effect=fake_urlopen):
                repaired=fetch_pdf_conditional(url,stock_id="8046",raw_root=root,retries=1)
            self.assertEqual(repaired.fetch_mode,"FULL_GET")
            self.assertFalse(repaired.changed)
            self.assertEqual(repaired.sha256,first.sha256)
            self.assertEqual(cached_path.read_bytes(),b"%PDF-stable")
            self.assertNotIn("if-none-match",calls[0])

    def test_cache_manifest_uses_portable_relative_paths(self):
        class Response:
            headers={}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return b"%PDF-stable"

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            url="https://example.com/report.pdf"
            with patch("scripts.extract_abf_operating_candidates.urlopen",return_value=Response()):
                fetched=fetch_pdf_conditional(url,stock_id="8046",raw_root=root,retries=1)
            manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["documents"][f"8046|{url}"]["relative_path"],f"8046/{fetched.sha256}.pdf")

    def test_malformed_cache_manifest_is_rebuilt_after_fresh_download(self):
        class Response:
            headers={"ETag":"\"abc\""}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return b"%PDF-stable"

        for payload in ('{"documents":', '[]', '{"documents":[]}', '{"documents":null}'):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                (root/"manifest.json").write_text(payload,encoding="utf-8")
                url="https://example.com/report.pdf"
                with patch("scripts.extract_abf_operating_candidates.urlopen",return_value=Response()) as request:
                    fetched=fetch_pdf_conditional(url,stock_id="8046",raw_root=root,retries=1)
                self.assertEqual(fetched.fetch_mode,"FULL_GET")
                headers={k.lower():v for k,v in request.call_args.args[0].header_items()}
                self.assertNotIn("if-none-match",headers)
                manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["documents"][f"8046|{url}"]["sha256"],fetched.sha256)

    def test_failed_manifest_replace_preserves_previous_cache_index(self):
        from scripts.extract_abf_operating_candidates import _save_raw_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            previous={"schema_version":"AbfDocumentCacheV1","documents":{}}
            _save_raw_manifest(root,previous)
            with patch.object(Path,"replace",side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    _save_raw_manifest(root,{"schema_version":"AbfDocumentCacheV1","documents":{"new":{}}})
            self.assertEqual(json.loads((root/"manifest.json").read_text(encoding="utf-8")),previous)

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
