from pathlib import Path
import csv
import unittest


class AbfDataSourceMapTests(unittest.TestCase):
    def test_every_requirement_has_source_mapping(self):
        import json
        req=json.loads(Path("data/abf_data_requirements.json").read_text(encoding="utf-8"))
        wanted={r["data_id"] for r in req["requirements"]}
        rows=list(csv.DictReader(Path("data/abf_data_source_map.csv").open(encoding="utf-8")))
        mapped={r["data_id"] for r in rows}
        self.assertTrue(wanted <= mapped, sorted(wanted-mapped))

    def test_upstream_registry_contains_key_free_sources(self):
        rows=list(csv.DictReader(Path("data/abf_industry_source_registry.csv").open(encoding="utf-8")))
        ids={r["source_id"] for r in rows}
        for source_id in (
            "tpca_industry_history","moea_glass_cloth_product","ajinomoto_abf_ir",
            "fred_copper","worldbank_copper","twse_major_info","twse_forecast_attainment",
        ):
            self.assertIn(source_id,ids)

    def test_consensus_eps_is_not_silently_replaced(self):
        rows={r["data_id"]:r for r in csv.DictReader(Path("data/abf_data_source_map.csv").open(encoding="utf-8"))}
        self.assertIn("TEJ",rows["consensus_eps"]["best_source"])
        self.assertIn("proxy",rows["consensus_eps"]["collection_action"].lower())


if __name__=="__main__":
    unittest.main()
