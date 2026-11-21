from io import StringIO
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from core import research_workspace as workspace
from core.research_workspace import ResearchDataset


def sample():
    rows = []
    for metric, shift in (("driver", 0), ("target", 1)):
        for i in range(14):
            month = pd.Period("2024-01", freq="M") + i + shift
            rows.append({
                "metric_id": metric, "period": str(month),
                "published_at": str((month + 1).start_time.date()),
                "change_pct": float((i * 5) % 13), "source": "fixture",
                "source_url": "https://example.org/series",
                "knowledge_time_method": "page_publication_date",
            })
    return pd.DataFrame(rows)


class ResearchWorkspaceTests(unittest.TestCase):
    def test_csv_import_preserves_numeric_metric_ids(self):
        csv = sample().replace({"driver": "0050", "target": "0062"}).to_csv(index=False)
        imported = ResearchDataset.from_csv(StringIO(csv))
        self.assertEqual(imported.metrics, ("0050", "0062"))

    def test_rejects_missing_provenance_and_pre_month_end_dates(self):
        raw = sample()
        missing = raw.copy()
        missing.loc[0, "source_url"] = " "
        with self.assertRaisesRegex(ValueError, "來源"):
            ResearchDataset(missing)
        raw.loc[0, "published_at"] = "2023-12-01"
        with self.assertRaisesRegex(ValueError, "月底"):
            ResearchDataset(raw)

    def test_snapshot_works_without_a_git_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file = root / "data/research_workspace_snapshot.csv"
            file.parent.mkdir()
            sample().to_csv(file, index=False)
            dataset = workspace.load_default_dataset(root)
            self.assertEqual(dataset.metrics, ("driver", "target"))

    def test_scan_and_pair_preserve_proxy_warning(self):
        raw = sample()
        raw.loc[0, "knowledge_time_method"] = "regulatory_deadline_proxy"
        dataset = ResearchDataset(raw)
        report = dataset.analyze("driver", "target", 1, "spearman")
        self.assertTrue(report.uses_proxy)
        cell = next(row for row in dataset.scan("target", "spearman") if row[1] == 1)
        self.assertTrue(cell[-1])

    def test_positive_month_lag_aligns_x_to_future_y_and_preserves_sources(self):
        report = ResearchDataset(sample()).analyze("driver", "target", 1, "spearman")
        self.assertAlmostEqual(report.coefficient, 1.0)
        self.assertEqual(len(report.samples), 14)
        self.assertEqual(len(report.rolling.dropna()), 3)
        self.assertEqual(str(report.samples.iloc[0]["target_period"]), "2024-02")
        self.assertEqual(report.samples.iloc[0]["feature_source_url"], "https://example.org/series")

    def test_rejects_duplicate_months_in_a_series(self):
        raw = sample()
        with self.assertRaisesRegex(ValueError, "重複"):
            ResearchDataset(pd.concat([raw, raw.iloc[:1]], ignore_index=True))

    def test_filters_months_where_the_driver_was_published_after_the_target(self):
        raw = sample()
        raw.loc[0, "published_at"] = "2025-04-01"
        report = ResearchDataset(raw).analyze("driver", "target", 1, "pearson")
        self.assertEqual(len(report.samples), 13)
        self.assertNotIn("2024-01", report.samples["period_m"].astype(str).tolist())

    def test_split_and_rolling_use_only_aligned_observations(self):
        raw = sample()
        raw.loc[raw["metric_id"] == "target", "change_pct"] = 1
        report = ResearchDataset(raw).analyze("driver", "target", 1, "spearman")
        self.assertIsNone(report.coefficient)
        self.assertIsNone(report.later)
        self.assertTrue(report.rolling.isna().all())
