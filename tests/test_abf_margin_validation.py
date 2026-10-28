from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from core.abf_margin_validation import validate_margin_transmission


COMPANIES = ("3037.TW", "3189.TW", "8046.TW")


def panel(*, quarters=84, companies=COMPANIES, acquired=None, slope=0.3, monthly_proof=False):
    rows = []
    # Alternating signs give both predeclared sides observations in every fold.
    for company in companies:
        revenues, margins = [], []
        for index, date in enumerate(pd.date_range("2002-03-31", periods=quarters, freq="QE")):
            magnitude = (1 + (index * 17) % 29) / 100
            growth = magnitude * (1 if index % 2 else -1)
            known = (date + pd.Timedelta(days=42)).tz_localize("Asia/Taipei")
            revenues.append(revenues[index - 4] * (1 + growth) if index >= 4 else 1000 + index)
            margins.append((margins[-1] if margins else 0.2) + growth * slope)
            rows.append({
                "ticker": company, "report_date": date.date().isoformat(),
                "available_date": known.date().isoformat(),
                "monthly_revenue_available_date": (date + pd.Timedelta(days=10)).date().isoformat(),
                "filing_published_at": known.isoformat(),
                "snapshot_acquired_at": acquired or known.isoformat(),
                "financial_evidence_acquired_at": acquired or known.isoformat(),
                "financial_basis_verification_available_at": known.isoformat(),
                "financial_release_date": known.date().isoformat(),
                "fundamental_source_url": "https://provider.example/financials",
                "primary_financial_source_url": "https://issuer.example/filing.pdf",
                "financial_evidence_id": f"{company}:{date.date().isoformat()}",
                "financial_value_verification": "MATCH",
                "accounting_basis": "STANDALONE_QUARTER", "financial_pit_exact": True,
                "monthly_revenue_3m_yoy": growth, "revenue_yoy": growth,
                "revenue": revenues[-1], "gross_margin": margins[-1],
                "gross_profit": revenues[-1] * margins[-1],
                "gross_margin_qoq": growth * slope,
                "gross_margin_yoy_delta": margins[-1] - margins[index - 4] if index >= 4 else np.nan,
            })
            if monthly_proof:
                monthly_known = (date + pd.Timedelta(days=10)).tz_localize("Asia/Taipei")
                rows[-1].update({
                    "monthly_source_release_date": monthly_known.date().isoformat(),
                    "monthly_revenue_source_url": "https://issuer.example/monthly-revenue",
                    "monthly_revenue_value_verification": "MATCH",
                    "monthly_revenue_accounting_basis": "CONSOLIDATED_MONTHLY_REVENUE",
                    "monthly_revenue_evidence_id": f"monthly:{company}:{date.date().isoformat()}",
                    "monthly_revenue_verification_available_at": monthly_known.isoformat(),
                    "monthly_revenue_acquired_at": acquired or monthly_known.isoformat(),
                    "monthly_revenue_pit_exact": True,
                })
    return pd.DataFrame(rows)


def comparison(audit, **wanted):
    defaults = dict(company="3037.TW", scenario="UPSIDE", feature="monthly_revenue_3m_yoy",
                    target="gross_margin_qoq", lag_quarters=0)
    defaults.update(wanted)
    return next(row for row in audit["comparisons"] if all(row[k] == v for k, v in defaults.items()))


class AbfMarginValidationTests(unittest.TestCase):
    def test_current_acquisition_prevents_a_validated_historical_training_set(self):
        audit = validate_margin_transmission(panel(acquired="2026-10-24T08:00:00Z"),
                                             as_of="2026-10-26", iterations=19)
        self.assertEqual(audit["contract"], "ABFMarginValidationV1")
        self.assertTrue(all(row["forecast_beta"] is None for row in audit["comparisons"]))
        self.assertTrue(all(not row["gates"]["oos_stability"] for row in audit["comparisons"]))
        for fold in comparison(audit)["oos_folds"]:
            self.assertEqual(fold["train_sample_size"], 0)
            self.assertFalse(fold["valid"])

    def test_all_hypotheses_and_separate_families_are_retained_even_without_data(self):
        audit = validate_margin_transmission(pd.DataFrame(), as_of="2026-10-26", iterations=19)
        self.assertEqual(len(audit["comparisons"]), 72)
        self.assertEqual(len({r["comparison_id"] for r in audit["comparisons"]}), 72)
        for side in ("UPSIDE", "DOWNSIDE"):
            rows = [r for r in audit["comparisons"] if r["scenario"] == side]
            self.assertEqual(len(rows), 36)
            self.assertTrue(all(r["fdr_family_size"] == 36 and r["fdr_q"] == 1 for r in rows))
            self.assertTrue(all(r["sample_size"] == 0 and r["evidence_status"] == "UNKNOWN" for r in rows))

    def test_percentage_points_slope_and_all_sample_provenance_are_explicit(self):
        audit = validate_margin_transmission(panel(monthly_proof=True), as_of="2026-10-26", iterations=19)
        row = comparison(audit)
        self.assertAlmostEqual(row["descriptive_beta"], 0.3)
        self.assertEqual(row["descriptive_beta_status"], "ESTIMATED")
        self.assertEqual(row["descriptive_beta_units"], "GM_CHANGE_PP_PER_REVENUE_GROWTH_PP")
        self.assertEqual(row["data_status"], "DESCRIPTIVE_PROXY_ONLY")
        self.assertEqual(row["timing_class"], "COINCIDENT")
        self.assertTrue(row["is_proxy"])
        self.assertTrue(row["pit_exact"])
        self.assertIsNone(row["forecast_beta"])
        self.assertIn("COMPANY_TOTAL_PROXY", row["rejection_reasons"])
        sample = row["sample_rows"][0]
        self.assertAlmostEqual(sample["x"], sample["x_ratio"] * 100)
        self.assertAlmostEqual(sample["y"], sample["y_ratio"] * 100)
        self.assertEqual(sample["feature_value_source"], "PROVIDED_MONTHLY_FEATURE")
        self.assertEqual(sample["target_value_source"], "RAW_GROSS_MARGIN_ENDPOINTS")
        self.assertTrue(sample["source_urls"])
        self.assertTrue(sample["dependency_ids"])
        self.assertEqual(sample["accounting_basis"], "STANDALONE_QUARTER")
        for prefix in ("feature", "target"):
            for field in ("observation_date", "release_date", "available_at", "signal_generated_at"):
                self.assertIn(f"{prefix}_{field}", sample)

    def test_sign_scenarios_and_fixed_company_denominator(self):
        audit = validate_margin_transmission(panel(companies=("3037.TW",)),
                                             as_of="2026-10-26", iterations=19)
        up, down = comparison(audit), comparison(audit, scenario="DOWNSIDE")
        self.assertTrue(all(s["x"] > 0 for s in up["sample_rows"]))
        self.assertTrue(all(s["x"] < 0 for s in down["sample_rows"]))
        self.assertAlmostEqual(up["cross_company_sign_share"], 1 / 3)
        self.assertAlmostEqual(down["cross_company_sign_share"], 1 / 3)
        negative = validate_margin_transmission(panel(slope=-0.3), as_of="2026-10-26", iterations=19)
        self.assertLess(comparison(negative, scenario="DOWNSIDE")["spearman"], 0)
        self.assertFalse(comparison(negative, scenario="DOWNSIDE")["gates"]["expected_direction"])

    def test_calendar_dependencies_do_not_shift_across_missing_quarters(self):
        source = panel(quarters=24, companies=("3037.TW",))
        source = source[source["report_date"] != "2004-03-31"]
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        row = comparison(audit, feature="revenue_yoy", target="gross_margin_yoy_delta", lag_quarters=1)
        for sample in row["sample_rows"]:
            fq = pd.Period(sample["feature_observation_date"], freq="Q")
            tq = pd.Period(sample["target_observation_date"], freq="Q")
            self.assertEqual(tq.ordinal - fq.ordinal, 1)
            self.assertIn(f"3037.TW:{fq - 4}", sample["dependency_ids"])
            self.assertIn(f"3037.TW:{tq - 4}", sample["dependency_ids"])
            self.assertNotIn("3037.TW:2004Q1", sample["dependency_ids"])
        feature_dates = {s["feature_observation_date"] for s in row["sample_rows"]}
        self.assertNotIn("2005-03-31", feature_dates)

    def test_historical_folds_require_training_and_fixed_unconditional_boundaries(self):
        audit = validate_margin_transmission(panel(), as_of="2026-10-26", iterations=19)
        up, down = comparison(audit), comparison(audit, scenario="DOWNSIDE")
        self.assertTrue(up["gates"]["oos_stability"])
        self.assertEqual(len(up["oos_folds"]), 3)
        self.assertGreaterEqual(sum(f["valid"] for f in up["oos_folds"]), 2)
        self.assertEqual([f["test_start_period"] for f in up["oos_folds"]],
                         [f["test_start_period"] for f in down["oos_folds"]])
        for fold in up["oos_folds"]:
            self.assertGreaterEqual(fold["train_sample_size"], 6)
            self.assertGreaterEqual(fold["test_sample_size"], 3)
            self.assertLess(fold["train_last_label_known_at"], fold["test_first_feature_known_at"])
            self.assertAlmostEqual(fold["train_beta"], 0.3)

    def test_gap_aware_blocks_and_resampling_are_deterministic(self):
        source = panel(quarters=30)
        source = source[~source["report_date"].isin(["2004-03-31", "2005-09-30"])]
        first = validate_margin_transmission(source, as_of="2026-10-26", iterations=39)
        second = validate_margin_transmission(source.sample(frac=1, random_state=9), as_of="2026-10-26", iterations=39)
        first.pop("generated_at")
        second.pop("generated_at")
        self.assertEqual(first, second)
        for row in first["comparisons"]:
            for block in row["resampling_blocks"]:
                ordinals = [pd.Period(q, freq="Q").ordinal for q in block]
                self.assertTrue(all(b - a == 1 for a, b in zip(ordinals, ordinals[1:])))

    def test_missing_invalid_future_metadata_and_unknown_release_remain_honest(self):
        source = panel(quarters=12, companies=("3037.TW",))
        source["financial_release_date"] = None
        source["filing_published_at"] = None
        source["financial_pit_exact"] = False
        source.loc[0, "available_date"] = None
        source.loc[1, "snapshot_acquired_at"] = "not-a-time"
        source.loc[2, "snapshot_acquired_at"] = "2030-01-01T00:00:00Z"
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        for row in audit["comparisons"]:
            for sample in row["sample_rows"]:
                self.assertIsNone(sample["feature_release_date"])
                self.assertIsNone(sample["target_release_date"])
                self.assertFalse(sample["pit_exact"])
                self.assertTrue(all(not d.endswith(("2002Q1", "2002Q2", "2002Q3")) for d in sample["dependency_ids"]))
        self.assertGreater(audit["coverage"]["excluded_input_rows"], 0)

    def test_sources_accounting_dependencies_and_economic_availability_are_separate_gates(self):
        source = panel(quarters=36)
        source["fundamental_source_url"] = None
        source["primary_financial_source_url"] = None
        source["accounting_basis"] = "UNKNOWN"
        source["financial_value_verification"] = "UNVERIFIED"
        source["financial_pit_exact"] = False
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        row = comparison(audit, lag_quarters=1)
        self.assertFalse(row["gates"]["source"])
        self.assertFalse(row["gates"]["accounting"])
        self.assertFalse(row["gates"]["pit"])
        self.assertEqual(row["timing_class"], "LEADING_CANDIDATE")
        self.assertTrue(row["gates"]["leading_availability"])
        self.assertFalse(comparison(audit)["gates"]["leading_availability"])

    def test_sparse_and_constant_samples_have_no_uncertainty(self):
        source = panel(quarters=8)
        source["gross_margin_qoq"] = 0.01
        source["gross_margin"] = 0.2
        source["gross_profit"] = source["revenue"] * 0.2
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        row = comparison(audit)
        for key in ("spearman", "bootstrap_ci_low", "bootstrap_ci_high", "beta_ci_low", "beta_ci_high", "permutation_p"):
            self.assertIsNone(row[key])
        self.assertEqual(row["fdr_q"], 1)
        self.assertFalse(row["gates"]["minimum_samples"])

    def test_raw_calendar_values_override_precomputed_growth_and_margin_changes(self):
        source = panel(quarters=24)
        expected = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        source["revenue_yoy"] = 999
        source["gross_margin_qoq"] = -999
        source["gross_margin_yoy_delta"] = 999
        actual = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        for feature in ("monthly_revenue_3m_yoy", "revenue_yoy"):
            for target in ("gross_margin_qoq", "gross_margin_yoy_delta"):
                a = comparison(actual, feature=feature, target=target)
                b = comparison(expected, feature=feature, target=target)
                self.assertEqual(a["sample_size"], b["sample_size"])
                self.assertEqual(a["descriptive_beta"], b["descriptive_beta"])

    def test_impossible_observation_knowledge_and_timezone_ambiguity_are_excluded(self):
        source = panel(quarters=12, companies=("3037.TW",))
        for field in ("available_date", "filing_published_at", "snapshot_acquired_at",
                      "financial_evidence_acquired_at", "financial_basis_verification_available_at",
                      "financial_release_date"):
            source.loc[0, field] = "2001-01-01"
        source.loc[1, "snapshot_acquired_at"] = "2002-08-01T14:00:00"
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        self.assertEqual(audit["coverage"]["usable_input_rows"], 10)
        for row in audit["comparisons"]:
            self.assertTrue(all(not dep.endswith(("2002Q1", "2002Q2"))
                                for sample in row["sample_rows"] for dep in sample["dependency_ids"]))

    def test_bh_correction_is_computed_independently_in_complete_side_families(self):
        audit = validate_margin_transmission(panel(quarters=32), as_of="2026-10-26", iterations=19)
        for scenario in ("UPSIDE", "DOWNSIDE"):
            family = sorted((r for r in audit["comparisons"] if r["scenario"] == scenario),
                            key=lambda r: r["fdr_input_p"])
            expected = [min(1.0, r["fdr_input_p"] * 36 / rank) for rank, r in enumerate(family, 1)]
            expected = np.minimum.accumulate(expected[::-1])[::-1]
            for row, value in zip(family, expected):
                self.assertAlmostEqual(row["fdr_q"], value)

    def test_unknown_primary_release_is_not_filled_with_another_document_filing(self):
        source = panel(quarters=12, companies=("3037.TW",))
        source["financial_release_date"] = None
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        sample = comparison(audit)["sample_rows"][0]
        self.assertIsNone(sample["feature_release_date"])
        self.assertIsNone(sample["target_release_date"])
        self.assertIsNotNone(sample["dependency_rows"][0]["filing_published_at"])
        self.assertIsNotNone(sample["dependency_rows"][0]["snapshot_acquired_at"])

    def test_monthly_feature_does_not_borrow_quarterly_financial_proof(self):
        audit = validate_margin_transmission(panel(quarters=40, companies=("3037.TW",)),
                                             as_of="2026-10-26", iterations=19)
        row = comparison(audit)
        for gate in ("source", "accounting", "pit"):
            self.assertFalse(row["gates"][gate])
        sample = row["sample_rows"][0]
        self.assertIsNone(sample["feature_release_date"])
        self.assertEqual(sample["feature_source_urls"], [])
        self.assertFalse(sample["feature_accounting_verified"])
        self.assertFalse(sample["feature_pit_exact"])
        self.assertTrue(sample["target_source_verified"])
        self.assertTrue(sample["target_accounting_verified"])
        self.assertTrue(sample["target_pit_exact"])
        self.assertEqual(sample["target_accounting_basis"], "STANDALONE_QUARTER")
        self.assertTrue(sample["target_source_urls"])
        self.assertAlmostEqual(row["descriptive_beta"], 0.3)

    def test_independent_monthly_proof_and_acquisition_bounds_are_retained(self):
        source = panel(quarters=40, companies=("3037.TW",), monthly_proof=True)
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        row = comparison(audit)
        self.assertTrue(all(row["gates"][gate] for gate in ("source", "accounting", "pit")))
        sample = row["sample_rows"][0]
        self.assertEqual(sample["feature_source_urls"], ["https://issuer.example/monthly-revenue"])
        self.assertNotIn("https://issuer.example/monthly-revenue", sample["target_source_urls"])
        self.assertTrue(sample["feature_release_date"].startswith("2002-07-10"))
        self.assertTrue(sample["target_release_date"].startswith("2002-08-11"))
        self.assertEqual(sample["feature_accounting_basis"], "CONSOLIDATED_MONTHLY_REVENUE")
        source["monthly_revenue_snapshot_acquired_at"] = "2026-10-24T08:00:00Z"
        late = comparison(validate_margin_transmission(source, as_of="2026-10-26", iterations=19))
        self.assertFalse(late["gates"]["oos_stability"])
        self.assertTrue(all(s["feature_known_at"] == "2026-10-24T08:00:00+00:00" for s in late["sample_rows"]))
        self.assertTrue(all(f["train_sample_size"] == 0 for f in late["oos_folds"]))

    def test_monthly_verification_flags_are_independent_of_financial_flags(self):
        source = panel(quarters=24, companies=("3037.TW",), monthly_proof=True)
        source["monthly_revenue_value_verification"] = "UNVERIFIED"
        source["monthly_revenue_pit_exact"] = False
        source["monthly_revenue_source_url"] = None
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        monthly = comparison(audit)
        quarterly = comparison(audit, feature="revenue_yoy")
        self.assertTrue(all(not monthly["gates"][gate] for gate in ("source", "accounting", "pit")))
        self.assertTrue(all(quarterly["gates"][gate] for gate in ("source", "accounting", "pit")))

    def test_training_purges_features_whose_baseline_was_acquired_after_test(self):
        source = panel(companies=("3037.TW",))
        source.loc[11, "snapshot_acquired_at"] = "2025-01-01T00:00:00Z"
        audit = validate_margin_transmission(source, as_of="2026-10-26", iterations=19)
        fold = comparison(audit, feature="revenue_yoy", lag_quarters=1)["oos_folds"][0]
        self.assertEqual(fold["train_sample_size"], 17)
        self.assertLess(fold["train_last_feature_known_at"], fold["test_first_feature_known_at"])
        self.assertLess(fold["train_last_label_known_at"], fold["test_first_feature_known_at"])

    def test_iterations_and_as_of_are_validated(self):
        with self.assertRaises(ValueError):
            validate_margin_transmission(panel(), as_of="2026-10-26", iterations=18)
        with self.assertRaises(ValueError):
            validate_margin_transmission(panel(), as_of="invalid", iterations=19)


if __name__ == "__main__":
    unittest.main()
