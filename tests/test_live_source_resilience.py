from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.collect_free_evidence import collect_all, persist_if_changed
from scripts.validate_pipeline_continuity import validate_live


class LiveSourceResilienceTests(unittest.TestCase):
    def _config(self,path: Path,max_stale_hours: int=72) -> Path:
        cfg={
            "schema_version":"FreeEvidenceSourcesV2",
            "policy":"Latest-only endpoints are forward-collected. Collection time is the earliest allowed availability when an exact historical publication timestamp is unavailable.",
            "sources":[{
                "source_id":"tpex_monthly_revenue",
                "provider":"TPEx",
                "kind":"monthly_revenue_json",
                "url":"https://official.example/tpex",
                "market":"TPEx",
                "primary":True,
                "enabled":True,
                "allow_stale_fallback":True,
                "max_stale_hours":max_stale_hours,
            }],
        }
        path.write_text(json.dumps(cfg),encoding="utf-8")
        return path

    def _seed_snapshot(self,persistent_root: Path,collected_at: pd.Timestamp) -> None:
        payload=json.dumps([{
            "資料年月":"11508","公司代號":"3037","公司名稱":"欣興","產業別":"電子零組件業",
            "營業收入-當月營收":"12345678","營業收入-去年同月增減(%)":"25.5","營業收入-上月比較增減(%)":"5.2"
        }],ensure_ascii=False).encode("utf-8")
        persist_if_changed(
            persistent_root=persistent_root,source_id="tpex_monthly_revenue",payload=payload,
            collected_at=collected_at,extension="json",source_url="https://official.example/tpex",
        )

    def test_recent_last_known_good_is_used_but_flagged_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            persistent=root/"persistent"; artifacts=root/"artifacts"
            cfg=self._config(root/"config.json")
            seeded=pd.Timestamp.now(tz="UTC")-pd.Timedelta(hours=1)
            self._seed_snapshot(persistent,seeded)
            with patch("scripts.collect_free_evidence.fetch_bytes",side_effect=RuntimeError("network down")),                  patch.dict(os.environ,{"RESEARCH_PIPELINE_RUN_ID":"resilience-test"}):
                evidence,summary=collect_all(config_path=cfg,persistent_root=persistent,artifacts_dir=artifacts)

            self.assertEqual(summary["sources_stale"],1)
            self.assertEqual(summary["sources_usable"],1)
            self.assertEqual(summary["sources_error"],0)
            self.assertEqual(summary["sources"][0]["status"],"stale_fallback")
            self.assertLessEqual(summary["sources"][0]["stale_age_hours"],72)
            self.assertFalse(evidence.empty)
            self.assertEqual(set(evidence["retrieval_status"]),{"STALE_FALLBACK"})
            self.assertEqual(set(evidence["pipeline_run_id"]),{"resilience-test"})
            self.assertTrue(evidence["raw_sha256"].astype(str).str.len().eq(64).all())
            self.assertTrue(evidence["retrieval_error"].astype(str).str.contains("network down").all())
            published=pd.to_datetime(evidence["published_at"].iloc[0],utc=True)
            self.assertEqual(published,seeded)

    def test_expired_snapshot_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            persistent=root/"persistent"; artifacts=root/"artifacts"
            cfg=self._config(root/"config.json",max_stale_hours=72)
            self._seed_snapshot(persistent,pd.Timestamp.now(tz="UTC")-pd.Timedelta(hours=100))
            with patch("scripts.collect_free_evidence.fetch_bytes",side_effect=RuntimeError("network down")):
                evidence,summary=collect_all(config_path=cfg,persistent_root=persistent,artifacts_dir=artifacts)
            self.assertEqual(summary["sources_stale"],0)
            self.assertEqual(summary["sources_error"],1)
            self.assertTrue(evidence.empty)
            self.assertIn("exceeds max age",summary["sources"][0]["error"])

    def test_continuity_treats_stale_as_usable_but_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); baseline=root/"baseline"; current=root/"current"
            baseline.mkdir(); (current/"artifacts").mkdir(parents=True)
            old_status={"sources":[{"source_id":"tpex","status":"ok"}]}
            new_status={"sources":[{"source_id":"tpex","status":"stale_fallback"}]}
            (baseline/"free_evidence_collection_status.json").write_text(json.dumps(old_status),encoding="utf-8")
            (current/"artifacts"/"free_evidence_collection_status.json").write_text(json.dumps(new_status),encoding="utf-8")
            row={"source_id":"tpex","published_at":"2026-10-01T00:00:00Z"}
            pd.DataFrame([row]).to_csv(baseline/"free_evidence_latest.csv",index=False)
            pd.DataFrame([row]).to_csv(current/"artifacts"/"free_evidence_latest.csv",index=False)
            checks={c["name"]:c for c in validate_live(baseline,current)}
            self.assertTrue(checks["live_previously_healthy_sources_present"]["passed"])
            self.assertFalse(checks["live_sources_using_stale_fallback"]["passed"])
            self.assertEqual(checks["live_sources_using_stale_fallback"]["severity"],"DEGRADED")
            self.assertTrue(checks["live_latest_availability_not_regressed"]["passed"])


if __name__=="__main__":
    unittest.main()
