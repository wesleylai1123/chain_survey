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
                for kind, value in (("Revenue", revenue), ("GrossProfit", revenue * 0.4), ("CostOfGoodsSold", -revenue * 0.6), ("OperatingExpenses", revenue * 0.2), ("OperatingIncome", revenue * 0.2), ("TotalNonoperatingIncomeAndExpense", revenue * 0.01), ("PreTaxIncome", revenue * 0.21), ("TAX", revenue * 0.04), ("IncomeAfterTaxes", revenue * 0.15), ("EPS", 1 + i * 0.1)):
                    fs.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                for kind, value in (("TotalAssets", 300 + i), ("TotalLiabilities", 100 + i), ("TotalEquity", 200 + i), ("Inventories", 30 + i), ("AccountsReceivableNet", 20 + i), ("AccountsPayable", 15 + i), ("PropertyPlantAndEquipment", 120 + i)):
                    bs.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                q=date.quarter
                ytd_ocf=sum(25 + k for k in range(i-q+1, i+1))
                ytd_capex=-sum(10 + k for k in range(i-q+1, i+1))
                ytd_dep=sum(6 + 0.2*k for k in range(i-q+1, i+1))
                ytd_amort=sum(1 + 0.05*k for k in range(i-q+1, i+1))
                ytd_interest=sum(2 + 0.1*k for k in range(i-q+1, i+1))
                for kind, value in (("CashFlowsFromOperatingActivities", ytd_ocf), ("PropertyAndPlantAndEquipment", ytd_capex), ("Depreciation", ytd_dep), ("AmortizationExpense", ytd_amort), ("InterestExpense", ytd_interest)):
                    cf.append({"stock_id": stock, "date": date, "type": kind, "value": value})
                for month in range(1, 4):
                    revenue_month = ((date.month - 3 + month - 1) % 12) + 1
                    revenue_year = date.year if revenue_month <= date.month else date.year - 1
                    mr.append({"stock_id": stock, "date": date, "revenue": revenue / 3, "revenue_year": revenue_year, "revenue_month": revenue_month, "create_time": None})
            daily_dates = pd.date_range("2022-01-01", "2025-06-30", freq="B")
            for j, day in enumerate(daily_dates):
                prices.append({"stock_id": stock, "date": day, "close": 50 + sidx * 5 + j * 0.05, "price_basis": "ADJUSTED_CLOSE"})
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

    def test_cashflow_is_deaccumulated_and_quality_metrics_exist(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        alpha = dataset[dataset["stock_id"] == "1111"].reset_index(drop=True)
        self.assertAlmostEqual(alpha.loc[1, "operating_cash_flow"], 26.0)
        self.assertAlmostEqual(alpha.loc[1, "capex"], -11.0)
        self.assertEqual(alpha.loc[1, "cashflow_basis"], "DEACCUMULATED_FROM_YTD")
        for col in ("free_cash_flow","fcf_margin","cfo_to_net_income","accrual_ratio"):
            self.assertIn(col, dataset.columns)

    def test_working_capital_and_ttm_roe_are_explicit(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        for col in ("accounts_receivable","accounts_payable","dso_days","dio_days","dpo_days","cash_conversion_cycle_days","roe_ttm","roe_basis"):
            self.assertIn(col, dataset.columns)
        alpha = dataset[dataset["stock_id"] == "1111"].reset_index(drop=True)
        self.assertEqual(alpha.loc[4, "roe_basis"], "TTM_NET_INCOME_OVER_AVG_BEGIN_END_EQUITY")
        self.assertTrue(pd.notna(alpha.loc[4, "roe_ttm"]))

    def test_monthly_revenue_keeps_earlier_availability(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        q1 = dataset[(dataset["stock_id"]=="1111") & (dataset["report_date"]=="2022-03-31")].iloc[0]
        self.assertEqual(q1["monthly_revenue_available_date"], "2022-04-10")
        self.assertEqual(q1["monthly_revenue_availability_method"], "statutory_next_month_10d_proxy")
        self.assertEqual(q1["return_basis"], "ADJUSTED_CLOSE")
        self.assertEqual(q1["monthly_revenue_return_basis"], "ADJUSTED_CLOSE")
        self.assertTrue(pd.notna(q1["monthly_revenue_future_3m_return"]))

    def test_small_internal_universe_does_not_define_cycle(self):
        dataset = build_factor_validation_dataset(self.companies, *self.inputs)
        self.assertEqual(set(dataset["cycle"]), {"Unknown"})
        self.assertTrue(dataset["cycle_basis"].astype(str).str.startswith("DISABLED_INTERNAL_UNIVERSE_TOO_SMALL").all())

    def test_depreciation_and_non_operating_bridges_exist(self):
        dataset=build_factor_validation_dataset(self.companies,*self.inputs)
        for col in (
            "opex_to_revenue","non_operating_income_expense","non_operating_share_of_pretax",
            "effective_tax_rate","depreciation","amortization","depreciation_to_revenue",
            "capex_to_depreciation","asset_turnover_quarterly","interest_coverage_proxy"
        ):
            self.assertIn(col,dataset.columns)
        alpha=dataset[dataset["stock_id"]=="1111"].reset_index(drop=True)
        self.assertAlmostEqual(alpha.loc[1,"depreciation"],6.2)
        self.assertTrue(pd.notna(alpha.loc[1,"effective_tax_rate"]))


if __name__ == "__main__":
    unittest.main()
