from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.validate_pipeline_continuity import validate_abf, validate_history, validate_live


class PipelineContinuityTests(unittest.TestCase):
    def test_live_detects_row_collapse_and_period_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"artifacts").mkdir(parents=True)
            old_status={"sources":[{"source_id":"a","status":"ok"},{"source_id":"b","status":"ok"}]}
            new_status={"sources":[{"source_id":"a","status":"ok"}]}
            (baseline/"free_evidence_collection_status.json").write_text(json.dumps(old_status),encoding="utf-8")
            (current/"artifacts"/"free_evidence_collection_status.json").write_text(json.dumps(new_status),encoding="utf-8")
            pd.DataFrame([
                {"source_id":"a","published_at":"2026-09-01T00:00:00Z"},
                {"source_id":"a","published_at":"2026-10-01T00:00:00Z"},
                {"source_id":"b","published_at":"2026-10-01T00:00:00Z"},
                {"source_id":"b","published_at":"2026-10-02T00:00:00Z"},
            ]).to_csv(baseline/"free_evidence_latest.csv",index=False)
            pd.DataFrame([
                {"source_id":"a","published_at":"2026-09-01T00:00:00Z"},
            ]).to_csv(current/"artifacts"/"free_evidence_latest.csv",index=False)

            checks={c["name"]:c for c in validate_live(baseline,current)}
            self.assertFalse(checks["live_row_count_not_collapsed"]["passed"])
            self.assertEqual(checks["live_row_count_not_collapsed"]["severity"],"FAIL")
            self.assertFalse(checks["live_latest_availability_not_regressed"]["passed"])
            self.assertFalse(checks["live_previously_healthy_sources_present"]["passed"])

    def test_history_detects_deleted_keys_and_period_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"data"/"history").mkdir(parents=True)
            old=pd.DataFrame([
                {"source_id":"s","metric_id":"m","entity":"e","period":"2026-08","value":1},
                {"source_id":"s","metric_id":"m","entity":"e","period":"2026-09","value":2},
            ])
            new=pd.DataFrame([
                {"source_id":"s","metric_id":"m","entity":"e","period":"2026-08","value":1},
            ])
            old.to_csv(baseline/"free_industry_history_panel.csv",index=False)
            new.to_csv(current/"data"/"history"/"free_industry_history_panel.csv",index=False)
            checks={c["name"]:c for c in validate_history(baseline,current)}
            self.assertFalse(checks["history_append_only_keys_preserved"]["passed"])
            self.assertFalse(checks["history_row_count_non_decreasing"]["passed"])
            self.assertFalse(checks["history_latest_period_not_regressed"]["passed"])

    def test_history_allows_value_revision_when_keys_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"data"/"history").mkdir(parents=True)
            old=pd.DataFrame([{"source_id":"s","metric_id":"m","entity":"e","period":"2026-09","value":1}])
            new=pd.DataFrame([{"source_id":"s","metric_id":"m","entity":"e","period":"2026-09","value":1.1}])
            old.to_csv(baseline/"free_industry_history_panel.csv",index=False)
            new.to_csv(current/"data"/"history"/"free_industry_history_panel.csv",index=False)
            checks={c["name"]:c for c in validate_history(baseline,current)}
            self.assertTrue(checks["history_append_only_keys_preserved"]["passed"])
            self.assertTrue(checks["history_value_revisions_recorded"]["passed"])
            self.assertIn("revised_existing_rows=1",checks["history_value_revisions_recorded"]["detail"])

    def test_abf_detects_document_and_candidate_collapse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"artifacts").mkdir(parents=True)

            pd.DataFrame([{"stock_id":"3037","source_id":"s1","healthy":True}]).to_csv(baseline/"abf_source_health.csv",index=False)
            pd.DataFrame([{"stock_id":"3037","source_id":"s1","healthy":False}]).to_csv(current/"artifacts"/"abf_source_health.csv",index=False)
            pd.DataFrame([{"stock_id":"3037","status":"OK"} for _ in range(10)]).to_csv(baseline/"abf_document_extract_status.csv",index=False)
            pd.DataFrame([{"stock_id":"3037","status":"OK"} for _ in range(3)]).to_csv(current/"artifacts"/"abf_document_extract_status.csv",index=False)
            pd.DataFrame([{"stock_id":"3037","data_id":"abf_utilization_history"} for _ in range(10)]).to_csv(baseline/"abf_operating_candidates.csv",index=False)
            pd.DataFrame([{"stock_id":"3037","data_id":"abf_capacity_history"} for _ in range(2)]).to_csv(current/"artifacts"/"abf_operating_candidates.csv",index=False)

            checks={c["name"]:c for c in validate_abf(baseline,current)}
            self.assertFalse(checks["abf_processed_document_count_not_collapsed"]["passed"])
            self.assertEqual(checks["abf_processed_document_count_not_collapsed"]["severity"],"FAIL")
            self.assertFalse(checks["abf_previously_healthy_sources_present"]["passed"])
            self.assertFalse(checks["abf_candidate_count_reasonable"]["passed"])
            self.assertFalse(checks["abf_candidate_types_preserved"]["passed"])

    def test_missing_baseline_is_bootstrap_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"artifacts").mkdir(parents=True)
            checks=validate_live(baseline,current)
            self.assertEqual(len(checks),1)
            self.assertTrue(checks[0]["passed"])
            self.assertEqual(checks[0]["severity"],"INFO")


if __name__=="__main__":
    unittest.main()
