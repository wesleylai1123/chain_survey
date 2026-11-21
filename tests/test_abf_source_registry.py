from pathlib import Path
import csv
import unittest
from urllib.parse import urlparse


class AbfSourceRegistryTests(unittest.TestCase):
    def test_registry_uses_primary_https_company_or_regulator_hosts(self):
        rows=list(csv.DictReader(Path("data/abf_source_registry.csv").open(encoding="utf-8")))
        self.assertGreaterEqual(len(rows),12)
        allowed={
            "openapi.twse.com.tw",
            "doc.twse.com.tw","mops.twse.com.tw","mopsov.twse.com.tw",
            "webpro.twse.com.tw",
            "www.kinsus.com.tw","kinsus.com.tw",
            "www.nanyapcb.com.tw","nanyapcb.com.tw",
        }
        self.assertEqual({r["stock_id"] for r in rows},{"3037","3189","8046"})
        source_ids={r["source_id"] for r in rows}
        self.assertEqual(len(source_ids),len(rows))
        for row in rows:
            with self.subTest(source_id=row["source_id"]):
                parsed=urlparse(row["source_url"])
                self.assertEqual(parsed.scheme,"https")
                self.assertIn(parsed.hostname,allowed)
                self.assertEqual(row["primary"].lower(),"true")
                self.assertTrue(row["use_for"].strip())
                self.assertTrue(row["parser_type"].strip())
                self.assertTrue(row["refresh_cadence"].strip())
                self.assertTrue(row["health_selector"].strip())
                if row["fallback_source_id"].strip():
                    self.assertIn(row["fallback_source_id"],source_ids)

    def test_each_company_has_regulator_and_operating_source(self):
        rows=list(csv.DictReader(Path("data/abf_source_registry.csv").open(encoding="utf-8")))
        for stock_id in ("3037","3189","8046"):
            company=[r for r in rows if r["stock_id"]==stock_id]
            hosts={r["source_host"] for r in company}
            self.assertTrue(any(h.endswith("twse.com.tw") for h in hosts),stock_id)
            operating=";".join(r["use_for"] for r in company)
            self.assertIn("guidance",operating)
            self.assertIn("capacity",operating)


if __name__=="__main__":
    unittest.main()
