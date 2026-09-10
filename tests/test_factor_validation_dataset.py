import unittest

import pandas as pd

from core.factor_validation_dataset import build_factor_validation_dataset


class FactorValidationDatasetTests(unittest.TestCase):
    def setUp(self):
        self.companies = pd.DataFrame([
            {"name": "Alpha", "ticker": "1111.TW", "sector": "Electronics", "industry": "Test"},
            {"name": "Bravo", "ticker": "2222.TW", "sector": "Electronics", "industry": "Test"},
        ])
        dates = pd.date_range("2022-03-31", periods=8, freq="QE")
        fs, bs, cf, mr, prices, val = [], [], [], [], [], []
        for sidx, stock in enumerate(("1111", "2222")):
            for i, date in enumerate(dates):
                revenue = 100 + 10 * i + 5 * sidx
                for kind, value in (("Revenue", revenue), ("GrossProfit", revenue * 0.4), ("OperatingIncome", revenue * 0.2), ("IncomeAfterTaxes", revenue * 0.15), ("EPS", 1 + i * 0.1)):
                    fs.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                for kind, value in (("TotalAssets", 300 + i), ("TotalLiabilities", 100 + i), ("TotalEquity", 200 + i), ("Inventories", 30 + i)):
                    bs.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                for kind, value in (("CashFlowsFromOperatingActivities", 25 + i), ("PropertyAndPlantAndEquipment", -10 - i)):
                    cf.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                for month in range(1, 4):
                    revenue_month = ((date.month - 3 + month - 1) % 12) + 1
                    revenue_year = date.year if revenue_month <= date.month else date.year - 1
                    mr.append({"stock_id": stock, "date": date, "revenue": revenue / 3, "revenue_year": revenue_year, "revenue_month": revenue_month})
            daily_dates = pd.date_range("2022-01-01", "2025-06-30", freq="B")
            for j, day in enumerate(daily_dates):
                prices.append({"stock_id": stock, "date": day, "close": 50 + sidx * 5 + j * 0.05})
                val.append({"stock_id": stock, "date": day, "PER": 10 + sidx, "PBR": 2 + sidx * 0.1, "dividend_yield": 0.03})
        self.inputs = tuple(pd.DataFrame(x) for x in (fs, bs, cf, mr, prices, val))

    def test_builds_point_in_time_targets_and_factors(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        self.assertFalse(dataset.empty)
        self.assertIn("revenue_yoy", dataset.columns)
        self.assertIn("gross_margin", dataset.columns)
        self.assertIn("inventory_yoy", dataset.columns)
        self.assertIn("future_3m_return", dataset.columns)
        self.assertIn("cycle", dataset.columns)
        q1 = dataset[dataset["report_date"] == "2022-03-31"].iloc[0]
        self.assertEqual(q1["available_date"], "2022-05-30")
        self.assertEqual(q1["availability_method"], "report_date+60d_proxy")
        self.assertGreater(dataset["future_3m_return"].notna().sum(), 0)

    def test_yoy_is_calculated_inside_company(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        alpha = dataset[dataset["stock_id"] == "1111"].reset_index(drop=True)
        expected = alpha.loc[4, "revenue"] / alpha.loc[0, "revenue"] - 1
        self.assertAlmostEqual(alpha.loc[4, "revenue_yoy"], expected)


if __name__ == "__main__":
    unittest.main()
