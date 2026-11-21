from __future__ import annotations

import json
import unittest
from pathlib import Path


class LiveFreeEvidenceSourceRegistryTests(unittest.TestCase):
    def test_registry_is_forward_only_and_primary(self):
        payload=json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"],"FreeEvidenceSourcesV2")
        self.assertIn("forward-collected",payload["policy"])
        rows=payload["sources"]
        self.assertEqual(len(rows),5)
        self.assertTrue(all(bool(r.get("primary")) for r in rows))
        self.assertTrue(all(bool(r.get("enabled")) for r in rows))

    def test_moea_dataset_ids_are_explicit(self):
        payload=json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        by={r["source_id"]:r for r in payload["sources"]}
        self.assertEqual(by["moea_export_orders_info_comm"]["dataset_id"],"16361")
        self.assertEqual(by["moea_export_orders_electronics"]["dataset_id"],"16362")

    def test_latest_only_sources_never_claim_historical_publication_time(self):
        payload=json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        self.assertIn("Collection time",payload["policy"])

    def test_official_fallback_preserves_moea_currency_and_commodity_mapping(self):
        payload=json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        rows={r["dataset_id"]:r["official_fallback"] for r in payload["sources"] if r.get("provider")=="MOEA"}
        self.assertEqual(rows["16361"]["commodity_id"],"9")
        self.assertEqual(rows["16362"]["commodity_id"],"6")
        for fallback in rows.values():
            self.assertEqual(fallback["dataset_id"],"A050106010")
            self.assertEqual(fallback["unit"],"百萬美元")


if __name__=="__main__":
    unittest.main()
