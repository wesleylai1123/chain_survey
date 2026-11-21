from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_research_data_pipeline_summary import build_summary


class ResearchDataPipelineSummaryTests(unittest.TestCase):
    def _write(self, root: Path, pipeline: str, run_id: str, *, manifest_status="PASS", validation_status="PASS", continuity_status="PASS", checks=None):
        folder=root/"persistent"/"run_manifests"/pipeline
        folder.mkdir(parents=True,exist_ok=True)
        manifest={
            "status":manifest_status,
            "code_revision":"abc123",
            "checks":checks or [{"name":"ok","passed":True,"severity":"FAIL","detail":""}],
        }
        validation={"status":validation_status}
        continuity={"status":continuity_status}
        (folder/f"{run_id}.json").write_text(json.dumps(manifest),encoding="utf-8")
        (folder/f"{run_id}.validation.json").write_text(json.dumps(validation),encoding="utf-8")
        (folder/f"{run_id}.continuity.json").write_text(json.dumps(continuity),encoding="utf-8")

    def test_all_pass_is_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run_id="1-1"
            for p in ("live","abf","history"):
                self._write(root,p,run_id)
            payload,frame=build_summary(root,run_id)
            self.assertEqual(payload["overall_status"],"PASS")
            self.assertEqual(set(frame["manifest_status"]),{"PASS"})
            self.assertEqual(frame["checks_failed"].sum(),0)

    def test_degraded_continuity_is_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run_id="2-1"
            self._write(root,"live",run_id,continuity_status="DEGRADED")
            self._write(root,"abf",run_id)
            self._write(root,"history",run_id)
            payload,frame=build_summary(root,run_id)
            self.assertEqual(payload["overall_status"],"DEGRADED")
            self.assertEqual(frame.loc[frame["pipeline"]=="live","continuity_status"].iloc[0],"DEGRADED")

    def test_missing_pipeline_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run_id="3-1"
            self._write(root,"live",run_id)
            self._write(root,"abf",run_id)
            payload,frame=build_summary(root,run_id)
            self.assertEqual(payload["overall_status"],"FAIL")
            row=frame[frame["pipeline"]=="history"].iloc[0]
            self.assertEqual(row["manifest_status"],"MISSING")
            self.assertTrue(row["missing_files"])

    def test_failed_manifest_check_fails_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run_id="4-1"
            bad=[{"name":"bad","passed":False,"severity":"FAIL","detail":"x"}]
            self._write(root,"live",run_id,checks=bad)
            self._write(root,"abf",run_id)
            self._write(root,"history",run_id)
            payload,frame=build_summary(root,run_id)
            self.assertEqual(payload["overall_status"],"FAIL")
            self.assertEqual(frame.loc[frame["pipeline"]=="live","checks_failed"].iloc[0],1)


if __name__=="__main__":
    unittest.main()
