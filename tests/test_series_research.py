import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core import series_research


ROOT = Path(__file__).resolve().parents[1]


class SeriesImportTest(unittest.TestCase):
    def test_preview_uses_csv_quoting_bom_and_first_five_records(self):
        text = '\ufeffdate,"quoted, header"\n' + '\n'.join(
            f'2025-01-0{i},"value, {i}"' for i in range(1, 8)
        )
        self.assertEqual(series_research.preview_csv(text), {
            "headers": ["date", "quoted, header"],
            "rows": [[f"2025-01-0{i}", f"value, {i}"] for i in range(1, 6)],
        })
        self.assertEqual(series_research.preview_csv("\n"), {"headers": [], "rows": []})

    def test_import_preserves_finite_points_per_column_and_normalizes_time(self):
        text = (
            "period,price,volume,release\n"
            "2025-03,inf,3,invalid\n"
            "bad,99,99,2025-04-01\n"
            "2025-01,10,,2025-02-01T09:00:00+08:00\n"
            "2025-02,11,nan,\n"
        )
        price, volume = series_research.import_csv(
            text, "quotes.csv", "period", ["price", "volume"], "release", "Exchange", "TWD",
        )
        self.assertEqual(price["name"], "price")
        self.assertEqual(price["category"], "Imported")
        self.assertEqual(price["frequency"], "M")
        self.assertEqual(price["source"], "Exchange")
        self.assertEqual(price["unit"], "TWD")
        self.assertEqual(price["points"], [
            {"date": "2025-01-31", "value": 10, "available": "2025-02-01T01:00:00+00:00"},
            {"date": "2025-02-28", "value": 11, "available": None},
        ])
        self.assertEqual(volume["points"], [
            {"date": "2025-03-31", "value": 3, "available": None},
        ])
        self.assertNotEqual(price["id"], volume["id"])
        json.dumps([price, volume], allow_nan=False)

    def test_import_identity_is_stable_and_isolates_files_and_columns(self):
        text = "date,value,other\n2025-01-02,1,1\n"
        def identifier(content, filename, column="value"):
            return series_research.import_csv(content, filename, "date", [column])[0]["id"]

        original = identifier(text, "daily.csv")
        self.assertEqual(original, identifier(text, "daily.csv"))
        self.assertNotEqual(original, identifier(text, "other.csv"))
        self.assertNotEqual(original, identifier(text.replace(",1,1", ",2,1"), "daily.csv"))
        self.assertNotEqual(original, identifier(text, "daily.csv", "other"))

    def test_import_rejects_unknown_and_ambiguous_headers(self):
        with self.assertRaisesRegex(ValueError, "release"):
            series_research.import_csv("date,value\n", "x.csv", "date", ["value"], "release")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            series_research.preview_csv("date,value,value\n")

    def test_import_infers_calendar_granularity(self):
        cases = [
            ("2025-01-02\n2025-01-03\n2025-01-06", "D"),
            ("2025-01-31\n2025-02-28\n2025-04-30", "M"),
            ("2025-03-31\n2025-06-30\n2025-12-31", "Q"),
            ("2025-01-01\n2025-04-01\n2025-10-01", "Q"),
            ("2025-Q1", "Q"),
        ]
        for dates, expected_frequency in cases:
            with self.subTest(dates=dates):
                text = "date,value\n" + "\n".join(f"{date},1" for date in dates.splitlines())
                result, = series_research.import_csv(text, "x.csv", "date", ["value"])
                self.assertEqual(result["frequency"], expected_frequency)

    def test_import_infers_frequency_per_column_using_only_retained_dates(self):
        text = (
            "date,daily,monthly\n2025-01-31,1,10\n2025-02-03,2,\n2025-02-04,3,NaN\n"
            "2025-02-28,,20\n2025-03-31,,30\n"
        )
        daily, monthly = series_research.import_csv(text, "mixed.csv", "date", ["daily", "monthly"])
        self.assertEqual((daily["frequency"], monthly["frequency"]), ("D", "M"))

    def test_import_honors_explicit_cadence_and_coarsest_retained_label(self):
        text = "date,x,y\n2025/1,1,\n2025-02-01,2,10\n2025-02-02,,20\n"
        monthly, daily = series_research.import_csv(text, "mixed.csv", "date", ["x", "y"])
        self.assertEqual((monthly["frequency"], daily["frequency"]), ("M", "D"))
        self.assertEqual([p["date"] for p in monthly["points"]], ["2025-01-31", "2025-02-01"])
        with self.assertRaisesRegex(ValueError, "x"):
            series_research.import_csv(text, "mixed.csv", "date", ["x", "y"], frequency="D")
        quarterly, = series_research.import_csv(text, "mixed.csv", "date", ["x"], frequency="Q")
        self.assertEqual(quarterly["frequency"], "Q")
        self.assertNotEqual(quarterly["id"], monthly["id"])
        explicit_daily, = series_research.import_csv(
            "date,x\n2025-01-31,1\n2025-02-28,2\n",
            "daily.csv", "date", ["x"], frequency="D",
        )
        self.assertEqual(explicit_daily["frequency"], "D")
        with self.assertRaisesRegex(ValueError, "frequency"):
            series_research.import_csv(text, "mixed.csv", "date", ["x"], frequency="W")

    def test_import_provenance_is_exported_on_both_sides_of_each_pair(self):
        x_text, y_text = "date,x\n2025-02,1\n", "day,y\n2025-02,2\n"
        x, = series_research.import_csv(x_text, "original X.csv", "date", ["x"], source="Provider X")
        y, = series_research.import_csv(y_text, "original Y.csv", "day", ["y"], source="Provider Y")
        sample, = _analyze(x, y)["samples"]
        for side, series, text in (("x", x, x_text), ("y", y, y_text)):
            provenance = {
                "filename": f"original {side.upper()}.csv", "column": side,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            self.assertEqual(series["provenance"], provenance)
            self.assertEqual(sample[f"{side}_source"], f"Provider {side.upper()}")
            for key, value in provenance.items():
                self.assertEqual(sample[f"{side}_{key}"], value)

    def test_import_rejects_duplicate_dated_values(self):
        with self.assertRaisesRegex(ValueError, r"[Dd]uplicate.*2025-01-02"):
            series_research.import_csv(
                "date,value\n2025-01-02,1\n2025-01-02,2\n",
                "daily.csv", "date", ["value"],
            )

    def test_import_rejects_entire_selection_if_a_column_has_no_points(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            series_research.import_csv(
                "date,value,empty\n2025-01-02,1,NaN\nbad,3,4\n",
                "daily.csv", "date", ["value", "empty"],
            )

    def test_import_counts_omissions_per_column(self):
        series, = series_research.import_csv(
            "date,value,released\n2025-01-02,1,\n2025-01-03,,2025-01-04\nbad,3,2025-01-05\n",
            "daily.csv", "date", ["value"], "released",
        )
        self.assertEqual(series["import_summary"], {
            "rows_read": 3,
            "skipped_invalid_dates": 1,
            "skipped_missing_or_nonnumeric_values": 1,
            "missing_availability": 1,
        })


class BuiltinCatalogTest(unittest.TestCase):
    def test_catalog_matches_tracked_monthly_history_and_publication_method(self):
        with (ROOT / "data/research_workspace_snapshot.csv").open(encoding="utf-8") as handle:
            snapshot = list(csv.DictReader(handle))
        catalog = {series["id"]: series for series in series_research.builtin_catalog(ROOT)}
        self.assertGreaterEqual(len(catalog), len({row["metric_id"] for row in snapshot}))
        for row in snapshot:
            series = catalog[row["metric_id"]]
            point = next(p for p in series["points"] if p["date"].startswith(row["period"]))
            self.assertEqual(series["frequency"], "M")
            self.assertEqual(series["unit"], "%")
            self.assertEqual(point["value"], float(row["change_pct"]))
            self.assertEqual(point["timing"], row["knowledge_time_method"])
            recorded = datetime.fromisoformat(row["published_at"])
            if point["timing"] == "page_publication_date":
                self.assertEqual(point["available_from"], (recorded - timedelta(seconds=86399)).isoformat())
                recorded += timedelta(microseconds=999999)
                self.assertEqual(point["available_until"], recorded.isoformat())
            self.assertEqual(point["available"], recorded.isoformat())

    def test_catalog_uses_disclosed_standalone_quarters_and_audit_timing(self):
        catalog = series_research.builtin_catalog(ROOT)
        quarterly = next(series for series in catalog if series["id"] == "quarterly_revenue::3037.TW")
        self.assertEqual(quarterly["frequency"], "Q")
        self.assertEqual(quarterly["unit"], "TWD thousand")
        self.assertEqual([p["date"] for p in quarterly["points"]], [
            "2025-03-31", "2025-06-30", "2026-03-31", "2026-06-30",
        ])
        first = quarterly["points"][0]
        self.assertEqual(first["value"], 30089532)
        self.assertEqual(first["available"], "2026-10-25T23:30:51.476083+00:00")
        self.assertEqual(first["timing"], "audit_acquisition")
        json.dumps(catalog, allow_nan=False)

    def test_catalog_keeps_official_fx_and_raw_etf_history_with_acquisition_provenance(self):
        catalog = {series["id"]: series for series in series_research.builtin_catalog(ROOT)}
        fx, etf = catalog["cbc_usd_twd"], catalog["twse_0050_close"]
        self.assertEqual(fx["frequency"], "D")
        self.assertEqual(etf["frequency"], "D")
        self.assertEqual(fx["unit"], "TWD per USD")
        self.assertEqual(fx["points"][0]["date"], "2008-01-02")
        self.assertEqual(etf["points"][0]["date"], "2026-09-01")
        self.assertIn("unadjusted", etf["name"].lower())
        for series, value, domain in [(fx, 31.633, "cbc.gov.tw"), (etf, 108.45, "twse.com.tw")]:
            self.assertIn("historical", series["source"].lower())
            self.assertIn(domain, series["source_url"])
            point = next(p for p in series["points"] if p["date"] == "2026-09-01")
            self.assertEqual(point["value"], value)
            self.assertEqual(point["available"][:10], "2026-11-20")
            self.assertEqual(point["timing"], "OBSERVED_AT_ACQUISITION_NOT_ORIGINAL_PUBLICATION")

    def test_catalog_omits_official_fixture_with_no_finite_points(self):
        raw = '[{"日期":"20080102","NTD_USD":"--"}]'.encode()
        source_dir = ROOT / "tests/fixtures/taiwan_official"
        provenance = json.loads((source_dir / "provenance.json").read_text(encoding="utf-8"))
        record = next(row for row in provenance["sources"] if row["name"] == "cbc-fx")
        record.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "tests/fixtures/taiwan_official"
            fixtures.mkdir(parents=True)
            (fixtures / record["path"]).write_bytes(raw)
            (fixtures / "provenance.json").write_text(json.dumps({"sources": [record]}), encoding="utf-8")
            self.assertEqual(series_research.builtin_catalog(root), [])


def _series(rows, frequency="D", **metadata):
    return {
        "frequency": frequency,
        "points": [dict(zip(("date", "value", "available", "timing"), row)) for row in rows],
        **metadata,
    }


def _chart(series, **overrides):
    options = dict(frequency="M", aggregation="last", transform="level", start=None, end=None)
    return series_research.chart_data(series, **(options | overrides))


def _analyze(x, y, **overrides):
    options = dict(
        frequency="M", aggregation="last", x_transform="level", y_transform="level",
        start=None, end=None, lag=0, window=3, strict=False,
    )
    return series_research.analyze(x, y, **(options | overrides))


class ChartDataTest(unittest.TestCase):
    def test_daily_quotes_aggregate_explicitly_including_inclusive_quarters(self):
        series = _series([
            ("2025-01-03", 10), ("2025-01-10", 14), ("2025-01-31", 18),
            ("2025-02-03", 20), ("2025-04-01", 99),
        ])
        for aggregation, value in [("last", 18), ("mean", 14), ("sum", 42)]:
            with self.subTest(aggregation=aggregation):
                self.assertEqual(_chart(series, aggregation=aggregation, start="2025-01", end="2025-01-08"),
                                 [{"date": "2025-01-31", "value": value}])
        self.assertEqual(_chart(series, frequency="Q", aggregation="sum", end="2025-02-08"),
                         [{"date": "2025-03-31", "value": 62}])

    def test_resample_then_transform_uses_prior_history_and_respects_missing_bins(self):
        series = _series([
            ("2025-01-30", 15), ("2025-01-31", 20), ("2025-02-27", 30),
            ("2025-04-30", 50), ("2025-05-30", 100),
        ])
        self.assertEqual(_chart(series, transform="diff", start="2025-02-01"), [
            {"date": "2025-02-28", "value": 10},
            {"date": "2025-03-31", "value": None},
            {"date": "2025-05-31", "value": 50},
        ])
        self.assertEqual(_chart(series, transform="return", start="2025-02", end="2025-02"), [
            {"date": "2025-02-28", "value": 0.5},
        ])

    def test_yoy_compares_exact_prior_year_at_each_frequency(self):
        cases = [
            ("D", "2024-03-01", "2025-03-01"),
            ("M", "2024-02-29", "2025-02-28"),
            ("Q", "2024-03-31", "2025-03-31"),
        ]
        for frequency, prior, current in cases:
            with self.subTest(frequency=frequency):
                result = _chart(
                    _series([(prior, 10), (current, 20)], frequency),
                    frequency=frequency, transform="yoy", start=current,
                )
                self.assertEqual(result, [{"date": current, "value": 1.0}])
        leap = _series([("2023-02-28", 10), ("2024-02-29", 20)])
        self.assertEqual(_chart(leap, frequency="D", transform="yoy", start="2024-02-29"),
                         [{"date": "2024-02-29", "value": None}])

    def test_finer_frequency_is_unavailable_and_sparse_daily_spans_are_bounded(self):
        monthly = _series([("2025-01-31", 10), ("2025-02-28", 12)], "M")
        self.assertEqual(_chart(monthly, frequency="D"), [])
        sparse = _series([("0001-01-01", 10), ("9999-12-31", 12)])
        self.assertEqual(_chart(sparse, frequency="D"), [
            {"date": "0001-01-01", "value": 10},
            {"date": "0001-01-02", "value": None},
            {"date": "9999-12-31", "value": 12},
        ])

    def test_nonfinite_derived_values_do_not_escape_to_json(self):
        series = _series([("2025-01-03", 1e308), ("2025-01-10", 1e308), ("2025-02-01", 0)])
        self.assertEqual(_chart(series, aggregation="sum"), [
            {"date": "2025-01-31", "value": None}, {"date": "2025-02-28", "value": 0},
        ])
        flat = _series([("2025-01-31", 0), ("2025-02-28", 42)], "M")
        self.assertEqual(_chart(flat, transform="return"), [{"date": "2025-01-31", "value": None}])


class CrossSeriesAnalysisTest(unittest.TestCase):
    def test_independent_csv_dates_align_at_exact_positive_and_negative_calendar_lags(self):
        x, = series_research.import_csv(
            "feature_day,x\n2025-01,2\n2025-03,1\n2025-04,8\n", "x.csv", "feature_day", ["x"],
        )
        y, = series_research.import_csv(
            "target_day,y\n2025-01,6\n2025-02,4\n2025-03,99\n2025-04,2\n",
            "y.csv", "target_day", ["y"],
        )
        leading = _analyze(x, y, lag=1, start="2025-02-08", end="2025-04-01")
        self.assertEqual(leading["n"], 2)
        self.assertAlmostEqual(leading["pearson"], 1)
        self.assertAlmostEqual(leading["spearman"], 1)
        self.assertEqual([(p["x_date"], p["y_date"]) for p in leading["samples"]], [
            ("2025-01-31", "2025-02-28"), ("2025-03-31", "2025-04-30"),
        ])
        trailing = _analyze(x, y, lag=-1, end="2025-03-01")
        self.assertEqual([(p["x_date"], p["y_date"]) for p in trailing["samples"]], [
            ("2025-03-31", "2025-02-28"), ("2025-04-30", "2025-03-31"),
        ])
        self.assertEqual([r["lag"] for r in leading["lags"]], list(range(-6, 7)))
        self.assertEqual(next(r for r in leading["lags"] if r["lag"] == 1)["n"], leading["n"])

    def test_selected_lag_outside_fixed_scan_is_still_calculated(self):
        x = _series([("2025-01-31", 1), ("2025-02-28", 2)], "M")
        y = _series([("2025-08-31", 10), ("2025-09-30", 20)], "M")
        result = _analyze(x, y, lag=7)
        self.assertEqual(result["n"], 2)
        self.assertEqual([r["lag"] for r in result["lags"]], list(range(-6, 7)))

    def test_zero_lag_and_rolling_are_measured_on_aligned_target_samples(self):
        periods = ["2025-01-31", "2025-02-28", "2025-04-30", "2025-05-31"]
        x = _series(list(zip(periods, [1, 4, 2, 3])), "M")
        y = _series(list(zip(periods, [10, 40, 20, 30])), "M")
        result = _analyze(x, y, lag=0)
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["pearson"], 1)
        self.assertAlmostEqual(result["spearman"], 1)
        self.assertEqual([s["y_date"] for s in result["samples"]], periods)
        self.assertEqual(result["rolling"][:2], [
            {"date": day, "pearson": None, "spearman": None} for day in periods[:2]
        ])
        self.assertAlmostEqual(result["rolling"][2]["pearson"], 1)
        self.assertAlmostEqual(result["rolling"][2]["spearman"], 1)
        json.dumps(result, allow_nan=False)

    def test_pearson_handles_a_large_offset_and_extreme_finite_values(self):
        dates = ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]
        for values, targets in (
            ([1e16 + offset for offset in (0, 2, 4, 6)], [0, 2, 4, 6]),
            ([-1.5e308, -5e307, 5e307, 1.5e308], [-3, -1, 1, 3]),
            ([5e-324, 1e-323, 1.5e-323, 2e-323], [1, 2, 3, 4]),
        ):
            with self.subTest(values=values):
                result = _analyze(_series(zip(dates, values), "M"), _series(zip(dates, targets), "M"))
                self.assertAlmostEqual(result["pearson"], 1.0, places=14)
                self.assertAlmostEqual(result["lags"][6]["pearson"], 1.0, places=14)
                for row in result["rolling"][2:]:
                    self.assertAlmostEqual(row["pearson"], 1.0, places=14)
                if values[0] == 1e16:
                    self.assertEqual([row["pearson"] for row in result["rolling"][2:]], [1.0, 1.0])

    def test_strict_compares_latest_x_with_earliest_y_for_date_only_csv(self):
        x, = series_research.import_csv(
            "date,x,release\n2025-01-01,1,2025-01-02\n2025-01-02,2,2025-01-02\n"
            "2025-01-03,3,2025-01-03T08:00:00Z\n", "x.csv", "date", ["x"], "release",
        )
        y, = series_research.import_csv(
            "date,y,release\n2025-01-01,1,2025-01-02T08:00:00Z\n2025-01-02,2,2025-01-03T08:00:00Z\n"
            "2025-01-03,3,2025-01-03\n", "y.csv", "date", ["y"], "release",
        )
        strict = _analyze(x, y, frequency="D", strict=True)
        self.assertEqual([sample["x_date"] for sample in strict["samples"]], ["2025-01-02"])
        self.assertEqual(strict["lags"][6]["n"], 1)
        self.assertEqual(strict["samples"][0]["x_available_from"], "2025-01-02T00:00:00+00:00")
        self.assertEqual(strict["samples"][0]["x_available_until"], "2025-01-02T23:59:59.999999+00:00")
        sample = _analyze(x, y, frequency="D")["samples"][2]
        self.assertEqual(sample["y_available_from"], "2025-01-03T00:00:00+00:00")
        self.assertEqual(sample["y_available_until"], "2025-01-03T23:59:59.999999+00:00")

    def test_date_only_bounds_propagate_through_aggregation_bin_close_and_difference(self):
        x = _series([
            ("2025-01-31", 1, "2025-02-02"),
            ("2025-02-15", 2, "2025-02-16T15:15:00Z"),
            ("2025-02-28", 3, "2025-03-02"),
        ])
        y = _series([("2025-02-28", 2, "2025-03-02T08:00:00Z")], "M")
        kwargs = dict(aggregation="sum", x_transform="diff")
        self.assertEqual(_analyze(x, y, strict=True, **kwargs)["n"], 0)
        sample, = _analyze(x, y, **kwargs)["samples"]
        self.assertEqual(sample["x_available_from"], "2025-03-02T00:00:00+00:00")
        self.assertEqual(sample["x_available_until"], "2025-03-02T23:59:59.999999+00:00")
        x["points"][-1]["available"] = "2025-02-28"
        sample, = _analyze(x, y, strict=True, **kwargs)["samples"]
        self.assertEqual(sample["x_available"], "2025-02-28T23:59:59.999999+00:00")
        self.assertNotIn("x_available_from", sample)

    def test_legacy_imported_midnight_is_ambiguous_but_new_exact_midnight_is_preserved(self):
        legacy = _series([("2025-01-01", 1, "2025-01-02T00:00:00+00:00")], category="Imported")
        current, = series_research.import_csv(
            "date,x,release\n2025-01-01,1,2025-01-02T00:00:00Z\n",
            "x.csv", "date", ["x"], "release",
        )
        target = _series([("2025-01-01", 1, "2025-01-02T08:00:00Z")])
        self.assertEqual(_analyze(legacy, target, frequency="D", strict=True)["n"], 0)
        self.assertEqual(_analyze(current, target, frequency="D", strict=True)["n"], 1)

    def test_tpca_date_precision_uses_taipei_local_day(self):
        tpca = next(s for s in series_research.builtin_catalog(ROOT) if s["id"] == "ccl_export_yoy")
        first = tpca["points"][0]
        y = _series([(first["date"], 1, "2024-02-20T00:00:00Z")], "M")
        sample, = _analyze(tpca, y)["samples"]
        self.assertEqual(sample["x_available_from"], "2024-02-19T16:00:00+00:00")
        self.assertEqual(sample["x_available_until"], "2024-02-20T15:59:59.999999+00:00")
        self.assertEqual(_analyze(tpca, y, strict=True)["n"], 0)
        self.assertEqual(_analyze(y, tpca, strict=True)["n"], 0)
        prior = _series([(first["date"], 1, "2024-02-19T15:59:59Z")], "M")
        self.assertEqual(_analyze(prior, tpca, strict=True)["n"], 1)

    def test_strict_zero_lag_requires_both_recorded_times_in_chronological_order(self):
        x = _series([
            ("2025-01-31", 1, "2025-02-10T09:00:00+08:00", "actual_publication_time"),
            ("2025-02-28", 2, "2025-03-10"),
            ("2025-03-31", 3),
            ("2025-04-30", 4, "2025-05-01", "regulatory_deadline_proxy"),
            ("2025-05-31", 5, "2025-06-01"),
            ("2025-06-30", 6, "2025-07-01"),
        ], "M")
        y = _series([
            ("2025-01-31", 4, "2025-02-10T01:00:00Z"),
            ("2025-02-28", 7, "2025-03-01"),
            ("2025-03-31", 2, "2025-04-10"),
            ("2025-04-30", 1, "2025-05-02"),
            ("2025-05-31", 8, "2025-06-02", "audit_acquisition"),
            ("2025-06-30", 9),
        ], "M")
        descriptive, strict = _analyze(x, y), _analyze(x, y, strict=True)
        self.assertEqual(descriptive["n"], 6)
        self.assertEqual(strict["n"], 1)
        self.assertIsNone(strict["pearson"])
        self.assertIsNone(strict["spearman"])
        sample, = strict["samples"]
        self.assertEqual((sample["x_date"], sample["y_date"], sample["x"], sample["y"]),
                         ("2025-01-31", "2025-01-31", 1, 4))
        self.assertEqual(sample["x_available"], "2025-02-10T01:00:00+00:00")
        self.assertEqual(sample["y_available"], sample["x_available"])
        self.assertEqual(sample["x_timing"], "actual_publication_time")
        self.assertNotIn("x_available_from", sample)
        for keyword in ("proxy", "missing", "after"):
            self.assertTrue(any(keyword in warning.lower() for warning in descriptive["warnings"]), keyword)
        self.assertEqual(next(r for r in strict["lags"] if r["lag"] == 0)["n"], 1)

    def test_aggregates_and_transforms_propagate_contributing_availability(self):
        x = _series([
            ("2025-01-03", 10, "2025-03-03", "regulatory_deadline_proxy"),
            ("2025-01-31", 20, "2025-02-02"),
            ("2025-02-10", 30, "2025-03-10"),
            ("2025-02-28", 50, "2025-03-02"),
        ])
        y = _series([("2025-02-28", 1, "2025-03-04")], "M")
        summed = _analyze(x, y, aggregation="sum", x_transform="diff", start="2025-02")
        self.assertEqual(summed["samples"][0]["x"], 50)
        self.assertEqual(summed["samples"][0]["x_available"], "2025-03-10T23:59:59.999999+00:00")
        self.assertIn("proxy", summed["samples"][0]["x_timing"])
        self.assertEqual(_analyze(x, y, aggregation="sum", x_transform="diff", strict=True)["n"], 0)
        last = _analyze(x, y, aggregation="last", x_transform="diff", strict=True, start="2025-02")
        self.assertEqual(last["samples"][0]["x"], 30)
        self.assertEqual(last["samples"][0]["x_available"], "2025-03-02T23:59:59.999999+00:00")
        missing = _series([("2025-01-31", 20), ("2025-02-28", 50, "2025-03-02")], "M")
        self.assertIsNone(_analyze(missing, y, x_transform="diff")["samples"][0]["x_available"])
        self.assertEqual(_analyze(missing, y, x_transform="diff", strict=True)["n"], 0)

    def test_official_captures_align_at_zero_lag_only_as_descriptive_history(self):
        catalog = {series["id"]: series for series in series_research.builtin_catalog(ROOT)}
        etf, fx = catalog["twse_0050_close"], catalog["cbc_usd_twd"]
        descriptive = _analyze(etf, fx, frequency="D", lag=0)
        self.assertGreater(descriptive["n"], 10)
        self.assertEqual(descriptive["samples"][0]["x_date"], "2026-09-01")
        self.assertEqual(descriptive["samples"][0]["y_date"], "2026-09-01")
        self.assertEqual(descriptive["samples"][0]["x"], 108.45)
        self.assertEqual(descriptive["samples"][0]["y"], 31.633)
        self.assertEqual(descriptive["samples"][0]["x_source_url"], etf["source_url"])
        self.assertEqual(descriptive["samples"][0]["y_source_url"], fx["source_url"])
        self.assertTrue(any("acquisition" in w.lower() for w in descriptive["warnings"]))
        self.assertEqual(_analyze(etf, fx, frequency="D", lag=0, strict=True)["n"], 0)

    def test_sample_urls_follow_contributing_values_with_chronological_deduplication(self):
        first, second, default = "https://example.test/first", "https://example.test/second", "https://example.test/default"
        x = _series([
            ("2025-02-14", 3), ("2025-01-08", 2), ("2025-02-01", 5), ("2025-01-02", 1),
        ], source_url=default)
        for index, url in [(0, first), (1, second), (3, first)]:
            x["points"][index]["source_url"] = url
        y = _series([("2025-02-28", 8)], "M", source_url=default)
        summed, = _analyze(x, y, aggregation="sum", x_transform="diff")["samples"]
        self.assertEqual(summed["x_source_url"], " | ".join([first, second, default]))
        self.assertEqual(summed["y_source_url"], default)
        last, = _analyze(x, y)["samples"]
        self.assertEqual(last["x_source_url"], first)
        imported, = series_research.import_csv(
            "date,x\n2025-02,1\n", "x.csv", "date", ["x"], source="User-supplied source",
        )
        self.assertEqual(imported["source"], "User-supplied source")
        self.assertNotIn("x_source_url", _analyze(imported, y)["samples"][0])

    def test_downsampling_clamps_known_availability_to_utc_bin_close(self):
        x = _series([
            ("2025-01-02", 1, "2025-01-02"), ("2025-01-07", 2, "2025-01-07"),
            ("2025-02-12", 3), ("2025-03-15", 4, "2025-04-10"),
        ])
        y = _series([
            ("2025-01-31", 5, "2025-01-20"),
            ("2025-02-28", 6, "2025-03-01"),
            ("2025-03-31", 7, "2025-04-12"),
        ], "M")
        for aggregation in ("last", "mean", "sum"):
            with self.subTest(aggregation=aggregation):
                result = _analyze(x, y, aggregation=aggregation)
                jan, feb, mar = result["samples"]
                self.assertEqual(jan["x_available"], "2025-01-31T23:59:59.999999+00:00")
                self.assertEqual(jan["y_available_from"], "2025-01-20T00:00:00+00:00")
                self.assertEqual(jan["y_available"], "2025-01-20T23:59:59.999999+00:00")
                self.assertIsNone(feb["x_available"])
                self.assertEqual(mar["x_available"], "2025-04-10T23:59:59.999999+00:00")
                strict = _analyze(x, y, aggregation=aggregation, strict=True)
                self.assertEqual([s["x_date"] for s in strict["samples"]], ["2025-03-31"])

    def test_timing_warning_for_other_lags_is_explicitly_scoped_to_scan(self):
        x = _series([
            ("2025-01-31", 1, "2025-02-01", "regulatory_deadline_proxy"),
            ("2025-02-28", 2, "2025-03-01"),
        ], "M")
        y = _series([("2025-02-28", 3, "2025-03-02")], "M")
        result = _analyze(x, y, lag=0)
        proxy_warnings = [w for w in result["warnings"] if "proxy" in w]
        self.assertEqual(len(proxy_warnings), 1)
        self.assertTrue(proxy_warnings[0].startswith("Lag scan"), proxy_warnings)

    def test_constant_series_and_unsupported_upsampling_are_json_serializable(self):
        monthly = _series([("2025-01-31", 1), ("2025-02-28", 1)], "M")
        constant = _analyze(monthly, monthly)
        self.assertEqual(constant["n"], 2)
        self.assertIsNone(constant["pearson"])
        self.assertIsNone(constant["spearman"])
        daily = _analyze(monthly, monthly, frequency="D")
        self.assertEqual(daily["n"], 0)
        self.assertTrue(any("upsampl" in w.lower() for w in daily["warnings"]))
        json.dumps([constant, daily], allow_nan=False)


if __name__ == "__main__":
    unittest.main()
