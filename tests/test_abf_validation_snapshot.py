"""Financial snapshots acquired later cannot enter an earlier ABF calibration."""
import unittest
from unittest.mock import patch

import pandas as pd

from scripts import run_abf_semantics_validation as exporter


class AbfValidationSnapshotTests(unittest.TestCase):
    def test_acquisition_aliases_and_release_cap_historical_replay(self):
        rows = [dict(ticker='3037.TW', report_date='2026-06-30', available_date='2026-08-07', tag='known')]
        for field in ('acquired_at', 'first_seen_at', 'snapshot_acquired_at', 'filing_published_at', 'available_at'):
            rows.append(dict(rows[0], tag=field, **{field: '2026-10-26T00:00:00Z'}))
        selected = exporter.factor_known_at(pd.DataFrame(rows), as_of='2026-10-25T00:00:00Z')
        self.assertEqual(selected['tag'].tolist(), ['known'])

    def test_daily_availability_uses_taiwan_end_of_day(self):
        rows = pd.DataFrame([dict(ticker='3037.TW', report_date='2026-06-30', available_date='2026-08-07')])
        self.assertTrue(exporter.factor_known_at(rows, as_of='2026-08-07T15:59:58Z').empty)
        self.assertEqual(len(exporter.factor_known_at(rows, as_of='2026-08-07T16:00:00Z')), 1)

    def test_unknown_availability_and_future_observation_stay_out(self):
        rows = pd.DataFrame([
            dict(tag='missing', report_date='2026-06-30', available_date=None),
            dict(tag='future-observation', report_date='2026-12-31', available_date='2026-08-07'),
            dict(tag='future-observation-alias', report_date='2026-06-30', available_date='2026-08-07',
                 observation_date='2026-12-31T00:00:00Z'),
        ])
        self.assertTrue(exporter.factor_known_at(rows, as_of='2026-10-25T00:00:00Z').empty)

    def test_report_applies_snapshot_filter_before_margin_scan(self):
        rows = pd.DataFrame([dict(ticker='3037.TW', report_date='2026-06-30',
            available_date='2026-08-07', snapshot_acquired_at='2026-10-26T00:00:00Z')])
        with patch.object(exporter, 'scan_revenue_to_margin') as scan:
            result = exporter.build_report(pd.DataFrame(), rows, as_of='2026-10-25T00:00:00Z', iterations=19)
        scan.assert_not_called()
        self.assertTrue(all(c['stages'][1]['status'] == 'UNAVAILABLE' for c in result['calibration_handoff']))


if __name__ == '__main__':
    unittest.main()
