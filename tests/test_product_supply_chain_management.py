from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core.company_insights import get_company_product_dependency_view, get_downstream_partners
from core.impact_engine import simulate_event
from core.product_supply_chain_service import delete_managed_mapping, load_managed_mappings, upsert_managed_mapping


class ProductSupplyChainManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

        for filename in [
            "company_master.csv",
            "product_master.csv",
            "company_relationships.csv",
            "company_product_relationships.csv",
            "product_relationships.csv",
            "product_market_relationships.csv",
        ]:
            shutil.copy(ROOT / "data" / filename, self.data_dir / filename)

        self._write_csv(
            "product_supply_chain_mappings.csv",
            [
                "source_company",
                "source_product",
                "direction",
                "related_company",
                "relation",
                "weight",
                "rationale",
                "updated_at",
            ],
            [],
        )
        self._write_csv("macro_factors.csv", ["factor_id", "display_name", "category", "unit", "description"], [])
        self._write_csv(
            "macro_exposures.csv",
            ["factor_id", "entity_type", "entity_name", "exposure_direction", "weight", "rationale"],
            [],
        )
        (self.data_dir / "event_templates.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "packaging-demand-test",
                        "name": "測試封裝需求傳導",
                        "description": "Seed the product node so analyst-managed downstream mappings participate in propagation.",
                        "severity": 1.0,
                        "max_layers": 3,
                        "seed_rules": [
                            {
                                "match": {
                                    "source": "日月光投控",
                                    "relation": "produces",
                                    "target": "Advanced Packaging",
                                },
                                "impact_on": "target",
                                "sentiment": "positive",
                                "base_score": 0.9,
                                "sensitivity": 1.0,
                                "reason": "封裝需求增加。",
                            }
                        ],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def _write_csv(self, name: str, header: list[str], rows: list[list[object]]) -> None:
        with open(self.data_dir / name, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    def test_mapping_persists_reload_and_duplicate_validation(self) -> None:
        upsert_managed_mapping(
            source_company="日月光投控",
            source_product="Advanced Packaging",
            direction="downstream",
            related_company="小米",
            weight=0.77,
            rationale="測試新增品牌客戶關聯",
        )

        saved = load_managed_mappings()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved.iloc[0]["relation"], "customer_of")

        data_loader.clear_data_caches()
        reloaded = load_managed_mappings()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded.iloc[0]["related_company"], "小米")

        with self.assertRaises(ValueError):
            upsert_managed_mapping(
                source_company="日月光投控",
                source_product="Advanced Packaging",
                direction="downstream",
                related_company="小米",
                weight=0.6,
                rationale="重複資料應被擋下",
            )

    def test_mapping_merges_into_company_and_product_views(self) -> None:
        upsert_managed_mapping(
            source_company="日月光投控",
            source_product="Advanced Packaging",
            direction="downstream",
            related_company="小米",
            weight=0.77,
            rationale="封裝服務供應到品牌端",
        )

        downstream = get_downstream_partners("日月光投控")
        self.assertTrue(((downstream["company"] == "小米") & (downstream["source_dataset"] == "analyst_managed")).any())
        self.assertTrue((downstream["mapped_products"] == "Advanced Packaging").any())

        product_view = get_company_product_dependency_view("日月光投控")
        target_row = product_view[product_view["target"] == "小米"]
        self.assertFalse(target_row.empty)
        self.assertEqual(target_row.iloc[0]["target_type"], "company")
        self.assertEqual(target_row.iloc[0]["source_dataset"], "analyst_managed")

    def test_mapping_participates_in_event_propagation_and_can_be_deleted(self) -> None:
        upsert_managed_mapping(
            source_company="日月光投控",
            source_product="Advanced Packaging",
            direction="downstream",
            related_company="小米",
            weight=0.77,
            rationale="封裝需求增加可傳導到品牌端",
        )

        result = simulate_event("測試封裝需求傳導")
        impacted = result[result["company"] == "小米"]
        self.assertFalse(impacted.empty)
        self.assertTrue(impacted["path"].str.contains("customer_of").any())

        delete_managed_mapping(
            source_company="日月光投控",
            source_product="Advanced Packaging",
            direction="downstream",
            related_company="小米",
        )
        data_loader.clear_data_caches()
        reloaded = load_managed_mappings()
        self.assertTrue(reloaded.empty)


if __name__ == "__main__":
    unittest.main()
