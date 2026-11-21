from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import pandas as pd

from scripts.collect_abf_source_manifest import extract_links, load_registry


class AbfSourceManifestTests(unittest.TestCase):
    def test_extracts_pdf_and_video_links(self):
        html="""
        <html><body>
        <a href="/files/q4.pdf">2025 Q4 Investor Conference</a>
        <a href="https://webpro.twse.com.tw/video/123">Video</a>
        <a href="/news">News</a>
        </body></html>
        """
        rows=extract_links(html,"https://example.com/investor/index")
        by={r["document_label"]:r for r in rows}
        self.assertEqual(by["2025 Q4 Investor Conference"]["document_kind"],"PDF")
        self.assertEqual(by["Video"]["document_kind"],"VIDEO")
        self.assertEqual(by["2025 Q4 Investor Conference"]["document_url"],"https://example.com/files/q4.pdf")

    def test_registry_has_stable_parser_and_fallback_contract(self):
        frame=load_registry("data/abf_source_registry.csv")
        self.assertEqual(set(frame["stock_id"]),{"3037","3189","8046"})
        self.assertTrue(frame["parser_type"].astype(str).str.len().gt(0).all())
        self.assertTrue(frame["health_selector"].astype(str).str.len().gt(0).all())
        self.assertGreaterEqual((frame["source_host"]=="openapi.twse.com.tw").sum(),3)
        self.assertGreaterEqual(frame["fallback_source_id"].fillna("").ne("").sum(),6)

    def test_rejects_unknown_fallback(self):
        frame=pd.read_csv("data/abf_source_registry.csv",dtype={"stock_id":str})
        frame.loc[0,"fallback_source_id"]="does-not-exist"
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"registry.csv"
            frame.to_csv(path,index=False)
            with self.assertRaisesRegex(ValueError,"Unknown fallback"):
                load_registry(path)


if __name__=="__main__":
    unittest.main()
