from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_pipeline_run_manifest import build_manifest, classify_status
from scripts.collect_free_evidence import load_persisted_snapshot, persist_if_changed
from scripts.extract_abf_operating_candidates import extract_candidates_from_pages


class ResearchPipelineReproducibilityTests(unittest.TestCase):
    def test_same_raw_payload_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            first,digest1,changed1,canonical1=persist_if_changed(
                persistent_root=root,source_id="src",payload=b"same bytes",
                collected_at=pd.Timestamp("2026-10-03T00:00:00Z"),extension="bin",
                source_url="https://official.example/data",
            )
            second,digest2,changed2,canonical2=persist_if_changed(
                persistent_root=root,source_id="src",payload=b"same bytes",
                collected_at=pd.Timestamp("2026-10-03T01:00:00Z"),extension="bin",
                source_url="https://official.example/data",
            )
            self.assertTrue(changed1)
            self.assertFalse(changed2)
            self.assertEqual(digest1,digest2)
            self.assertEqual(first,second)
            self.assertEqual(canonical1,pd.Timestamp("2026-10-03T00:00:00Z"))
            self.assertEqual(canonical2,canonical1)
            restored=load_persisted_snapshot(persistent_root=root,source_id="src")
            self.assertIsNotNone(restored)
            _,_,_,restored_canonical,last_verified,_=restored
            self.assertEqual(restored_canonical,canonical1)
            self.assertEqual(last_verified,pd.Timestamp("2026-10-03T01:00:00Z"))
            manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sources"]["src"]["collected_at"],"2026-10-03T00:00:00+00:00")
            self.assertEqual(manifest["sources"]["src"]["last_verified_at"],"2026-10-03T01:00:00+00:00")
            self.assertEqual(len(list((root/"raw"/"src").glob("*.bin"))),1)

    def test_changed_raw_payload_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            first,d1,_,canonical1=persist_if_changed(
                persistent_root=root,source_id="src",payload=b"v1",
                collected_at=pd.Timestamp("2026-10-03T00:00:00Z"),extension="bin",
                source_url="https://official.example/data",
            )
            second,d2,changed,canonical2=persist_if_changed(
                persistent_root=root,source_id="src",payload=b"v2",
                collected_at=pd.Timestamp("2026-10-03T01:00:00Z"),extension="bin",
                source_url="https://official.example/data",
            )
            self.assertTrue(changed)
            self.assertNotEqual(d1,d2)
            self.assertNotEqual(first,second)
            self.assertEqual(canonical1,pd.Timestamp("2026-10-03T00:00:00Z"))
            self.assertEqual(canonical2,pd.Timestamp("2026-10-03T01:00:00Z"))

    def test_abf_processing_is_deterministic_for_same_page_text(self):
        kwargs=dict(
            stock_id="8046",company="Nan Ya PCB",source_id="nypcb_ir",
            document_url="https://official.example/report.pdf",
            pages=["ABF utilization 稼動率 80-90% and ABF 擴產 new line."],
            document_sha256="a"*64,use_for="utilization;capacity",
        )
        a=extract_candidates_from_pages(**kwargs)
        b=extract_candidates_from_pages(**kwargs)
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(set(a["review_status"]),{"CANDIDATE"})

    def test_manifest_status_is_fail_closed(self):
        self.assertEqual(classify_status([{"severity":"FAIL","passed":False}]),"FAIL")
        self.assertEqual(classify_status([{"severity":"DEGRADED","passed":False}]),"DEGRADED")
        self.assertEqual(classify_status([{"severity":"FAIL","passed":True}]),"PASS")

    def test_manifest_hashes_inputs_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.txt"
            p.write_text("stable",encoding="utf-8")
            manifest=build_manifest(
                "run-1","test",[p],[p],
                [{"name":"ok","severity":"FAIL","passed":True,"detail":""}],
            )
            self.assertEqual(manifest["status"],"PASS")
            self.assertEqual(len(manifest["inputs"][0]["sha256"]),64)
            self.assertEqual(manifest["inputs"][0]["sha256"],manifest["outputs"][0]["sha256"])


if __name__=="__main__":
    unittest.main()
