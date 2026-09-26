import unittest

import pandas as pd

from core.factor_validation_dataset import build_factor_validation_dataset
from core.filing_availability import verified_filing_times
from tests.test_factor_validation_dataset import FactorValidationDatasetTests


class FilingAvailabilityTests(unittest.TestCase):
    def test_exact_filing_overrides_only_matching_quarter(self):
        fixture = FactorValidationDatasetTests()
        fixture.setUp()
        filing = pd.DataFrame([{
            "stock_id": "1111", "report_date": "2022-03-31",
            "published_at": "2022-05-10T17:30:00+08:00",
            "source_url": "https://mops.twse.com.tw/example/1111/2022Q1",
            "document_type": "quarterly_financial_report",
            "document_name": "202201_1111_AI1.pdf",
        }])
        result = build_factor_validation_dataset(fixture.companies, *fixture.inputs, filing_observations=filing)
        exact = result[(result.stock_id == "1111") & (result.report_date == "2022-03-31")].iloc[0]
        other = result[(result.stock_id == "2222") & (result.report_date == "2022-03-31")].iloc[0]
        self.assertEqual(exact.available_date, "2022-05-11")
        self.assertEqual(exact.availability_method, "official_filing_timestamp_next_day")
        self.assertEqual(exact.filing_published_at, "2022-05-10T17:30:00+08:00")
        self.assertEqual(other.available_date, "2022-05-30")
        self.assertEqual(other.availability_method, "report_date+60d_proxy")

    def test_rejects_unverified_and_ambiguous_filing(self):
        row = {"stock_id": "3037", "report_date": "2025-03-31", "published_at": "2025-05-01T18:00:00+08:00", "source_url": "https://mops.twse.com.tw/example", "document_type": "quarterly_financial_report", "document_name": "202501_3037_AI1.pdf"}
        self.assertEqual(len(verified_filing_times(pd.DataFrame([row]))), 1)
        for change in ({"published_at": "2025-05-01"}, {"source_url": "https://example.com"}, {"document_type": "earnings_call"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verified_filing_times(pd.DataFrame([{**row, **change}]))
        with self.assertRaises(ValueError):
            verified_filing_times(pd.DataFrame([row, row]))

    def test_repository_has_complete_official_abf_filing_history(self):
        rows = pd.read_csv("data/abf_filing_observations.csv", dtype={"stock_id": str})
        verified = verified_filing_times(rows)
        self.assertEqual(len(verified), 78)
        self.assertEqual(verified.groupby("stock_id").size().to_dict(), {"3037": 26, "3189": 26, "8046": 26})
        self.assertEqual(verified["report_date"].min(), "2020-03-31")
        self.assertEqual(verified["report_date"].max(), "2026-06-30")


if __name__ == "__main__":
    unittest.main()
