from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from app.research_web import ResearchHandler, ResearchService


class ResearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Path(self.temp.name) / "catalog.sqlite3"
        self.service = ResearchService([], self.storage)

    def import_series(self, filename, values, service=None):
        csv = "day,value\n" + "\n".join(
            f"2025-{i + 1:02d}-20,{value}" for i, value in enumerate(values)
        )
        return (service or self.service).dispatch("/api/csv/import", {
            "text": csv, "filename": filename, "date_column": "day", "columns": ["value"],
        })["series"][0]

    def test_separate_imports_persist_and_support_correlation(self):
        x = self.import_series("first.csv", range(1, 11))
        y = self.import_series("second.csv", range(30, 0, -3))
        self.assertNotEqual(x["id"], y["id"])
        self.assertNotIn("points", x)
        reopened = ResearchService([], self.storage)
        self.assertEqual(len(reopened.catalog()["series"]), 2)
        pair = reopened.dispatch("/api/analyze", {
            "x": x["id"], "y": y["id"], "frequency": "M", "lag": 0,
        })
        self.assertEqual(pair["n"], 10)
        self.assertAlmostEqual(pair["pearson"], -1)
        self.assertAlmostEqual(pair["spearman"], -1)

    def test_instances_share_imports_without_losing_existing_series(self):
        second = ResearchService([], self.storage)
        first_series = self.import_series("first.csv", range(1, 5))
        second_series = self.import_series("second.csv", range(7, 11), second)
        expected = {first_series["id"], second_series["id"]}
        for service in (self.service, second, ResearchService([], self.storage)):
            self.assertEqual({item["id"] for item in service.catalog()["series"]}, expected)

    def test_explicit_csv_frequency_and_source_are_available_to_daily_analysis(self):
        imported = self.service.dispatch("/api/csv/import", {
            "text": "date,volume,margin\n2025-01-31,5,2\n2025-02-28,7,4\n2025-03-31,8,5",
            "filename": "statement.csv", "date_column": "date", "columns": ["volume", "margin"],
            "frequency": "D", "source": "Monthly statement downloaded from the issuer",
        })["series"]
        self.assertEqual([item["frequency"] for item in imported], ["D", "D"])
        x, y = [item["id"] for item in imported]
        result = self.service.dispatch("/api/analyze", {"x": x, "y": y, "frequency": "D"})
        self.assertEqual(result["n"], 3)
        self.assertAlmostEqual(result["pearson"], 1)
        sample = result["samples"][0]
        self.assertEqual(sample["x_source"], "Monthly statement downloaded from the issuer")
        self.assertEqual(sample["x_filename"], "statement.csv")
        self.assertEqual(sample["x_column"], "volume")
        self.assertEqual(sample["y_column"], "margin")
        self.assertRegex(sample["x_content_hash"], r"^[a-f0-9]{64}$")

    def test_invalid_option_is_rejected(self):
        x = self.import_series("first.csv", range(1, 11))
        with self.assertRaisesRegex(ValueError, "frequency"):
            self.service.dispatch("/api/chart", {"series": [{"id": x["id"]}], "frequency": "H"})

    def test_failed_import_preserves_catalog(self):
        self.import_series("first.csv", range(1, 11))
        with self.assertRaises(ValueError):
            self.service.dispatch("/api/csv/import", {
                "text": "date,a\n2025-01-01,no number", "filename": "invalid.csv",
                "date_column": "date", "columns": ["a"],
            })
        self.assertEqual(len(self.service.catalog()["series"]), 1)

    def test_server_blocks_cross_origin_imports_and_serves_only_expected_assets(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), ResearchHandler) as server:
            server.research = self.service
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    connection.request("POST", "/api/csv/preview", '{"text":"date,x"}',
                                       {"Origin": "https://external.example", "Content-Type": "application/json"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                    connection.request("GET", "/api/catalog")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    connection.request("GET", "/vendor/../index.html")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
                finally:
                    connection.close()
            finally:
                server.shutdown()
                thread.join()
