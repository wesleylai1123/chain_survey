from pathlib import Path
import csv
import unittest
from urllib.parse import urlparse


class AbfSourceRegistryTests(unittest.TestCase):
    def test_registry_uses_primary_https_company_or_regulator_hosts(self):
        rows=list(csv.DictReader(Path("data/abf_source_registry.csv").open(encoding="utf-8")))
        self.assertGreaterEqual(len(rows),6)
        allowed={
            "doc.twse.com.tw","mops.twse.com.tw","mopsov.twse.com.tw",
            "www.kinsus.com.tw","kinsus.com.tw",
            "www.nanyapcb.com.tw","nanyapcb.com.tw",
        }
        self.assertEqual({r["stock_id"] for r in rows},{"3037","3189","8046"})
        for row in rows:
            with self.subTest(url=row["source_url"]):
                parsed=urlparse(row["source_url"])
                self.assertEqual(parsed.scheme,"https")
                self.assertIn(parsed.hostname,allowed)
                self.assertEqual(row["primary"].lower(),"true")
                self.assertTrue(row["use_for"].strip())


if __name__=="__main__":
    unittest.main()
