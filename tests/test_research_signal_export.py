from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from core.research_signal_export import build_research_signals
from scripts import export_research_signals


ROOT = Path(__file__).resolve().parents[1]
ACQUIRED = "2026-10-04T00:00:00+00:00"
SHA = "a" * 40


def row(code: str, period: str = "2026-08", yoy: object = "12", **changes: object) -> dict:
    value = {
        "company": f"Company {code}",
        "ticker": f"{code}.TW",
        "period": period,
        "period_date": f"{period}-31T00:00:00+08:00",
        "published_at": "2026-09-10T23:59:59+08:00",
        "monthly_revenue": "1000",
        "yoy_pct": yoy,
        "source": "MOPS-derived test source",
        "source_url": "https://example.com/source",
        "knowledge_time_method": "regulatory_deadline_proxy",
        "transport": "finmind",
    }
    value.update(changes)
    return value


def build(rows: list[dict], **kwargs: object) -> list[dict]:
    return build_research_signals(
        rows,
        snapshot_acquired_at=ACQUIRED,
        as_of=ACQUIRED,
        commit_sha=SHA,
        input_snapshot_id="sha256:" + "b" * 64,
        stock_ids=("3037", "3189", "8046"),
        **kwargs,
    )


class ResearchSignalExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [row("3037"), row("3189", yoy="5"), row("8046", yoy="-1")]

    def test_acquisition_floor_proxy_and_schema(self) -> None:
        signals = build(self.rows)
        self.assertEqual([s["entity_id"] for s in signals], ["TWSE:3037", "TWSE:3189", "TWSE:8046"])
        self.assertEqual([s["rank"] for s in signals], [1, 2, 3])
        self.assertEqual(signals[0]["available_at"], ACQUIRED)
        self.assertEqual(signals[0]["signal_value"], 12.0)
        self.assertEqual(signals[0]["observation_period"], {"start": "2026-08-01", "end": "2026-08-31"})
        self.assertEqual(signals[0]["signal_id"], "monthly_revenue.yoy")
        self.assertTrue(signals[0]["is_estimate"])
        self.assertIn("regulatory_deadline_proxy", signals[0]["source_version"])
        schema = json.loads((ROOT / "contracts/research-signal/v1/schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for signal in signals:
            self.assertEqual(list(validator.iter_errors(signal)), [])

    def test_future_publication_is_excluded_and_latest_eligible_month_selected(self) -> None:
        rows = self.rows + [
            row("8046", period="2026-09", yoy="99", period_date="2026-09-30T00:00:00+08:00", published_at="2026-10-10T23:59:59+08:00"),
            row("3037", period="2026-07", yoy="88", period_date="2026-07-31T00:00:00+08:00"),
        ]
        signals = build(rows)
        self.assertEqual(next(s for s in signals if s["entity_id"] == "TWSE:8046")["signal_value"], -1.0)
        self.assertEqual(next(s for s in signals if s["entity_id"] == "TWSE:3037")["signal_value"], 12.0)

    def test_missing_company_or_cutoff_before_acquisition_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "8046"):
            build(self.rows[:2])
        with self.assertRaisesRegex(ValueError, "as_of"):
            build_research_signals(self.rows, snapshot_acquired_at=ACQUIRED, as_of="2026-10-03T00:00:00Z", commit_sha=SHA, input_snapshot_id="snapshot")

    def test_tie_break_identical_duplicates_and_unrelated_bad_rows(self) -> None:
        rows = [row("3189"), row("3037"), row("8046", yoy="-1"), row("3037"), row("9999", yoy="bad", period="invalid")]
        self.assertEqual([s["entity_id"] for s in build(rows)], ["TWSE:3037", "TWSE:3189", "TWSE:8046"])

    def test_bad_rows_rejected(self) -> None:
        bad = [
            ({"yoy_pct": "nan"}, "yoy"),
            ({"yoy_pct": True}, "yoy"),
            ({"period": "2026-13"}, "period"),
            ({"period_date": "2026-09-01T00:00:00+08:00"}, "period_date"),
            ({"published_at": "2026-09-10T23:59:59"}, "timezone"),
            ({"published_at": "2026-08-15T00:00:00+08:00"}, "publication"),
            ({"source_url": ""}, "source_url"),
            ({"source_url": "this is not a URL"}, "source_url"),
            ({"source_url": "https:///missing-host"}, "source_url"),
            ({"knowledge_time_method": "unverified_guess"}, "knowledge_time_method"),
        ]
        for changes, message in bad:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                build([dict(self.rows[0], **changes), *self.rows[1:]])
        with self.assertRaisesRegex(ValueError, "commit_sha"):
            build_research_signals(self.rows, snapshot_acquired_at=ACQUIRED, as_of=ACQUIRED, commit_sha="invalid", input_snapshot_id="snapshot")
        with self.assertRaisesRegex(ValueError, "timezone"):
            build_research_signals(self.rows, snapshot_acquired_at="2026-10-04T00:00:00", as_of=ACQUIRED, commit_sha=SHA, input_snapshot_id="snapshot")

    def test_conflicting_duplicate_and_candidate_exclusion(self) -> None:
        with self.assertRaisesRegex(ValueError, "conflicting"):
            build([*self.rows, row("3037", yoy="13")])
        with self.assertRaisesRegex(ValueError, "conflicting"):
            build([*self.rows, row("3037", monthly_revenue="1001")])
        excluded = [row("3037", period="2026-09", yoy="99", period_date="2026-09-30T00:00:00+08:00", review_status="CANDIDATE"), *self.rows]
        self.assertEqual(next(s for s in build(excluded) if s["entity_id"] == "TWSE:3037")["signal_value"], 12.0)
        for changes in ({"accepted": False}, {"review_status": "unreviewed"}):
            self.assertEqual(len(build([dict(self.rows[0], **changes), *self.rows])), 3)
        with self.assertRaisesRegex(ValueError, "3037"):
            build([dict(self.rows[0], status="NOT_ACCEPTED"), *self.rows[1:]])

    def test_direct_publication_time_is_reported(self) -> None:
        rows = [dict(item, knowledge_time_method="source_reported") for item in self.rows]
        signal = build(rows)[0]
        self.assertFalse(signal["is_estimate"])
        self.assertEqual(signal["confidence"], 1.0)

    def test_invalid_rfc3339_offsets_are_rejected(self) -> None:
        for stamp in ("2026-10-04T00:00:00+08:00:30", "2026-10-04T00:00:00+00:60", "2026-10-04T00:00:00+0800"):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                build_research_signals(self.rows, snapshot_acquired_at=stamp, as_of=stamp,
                    commit_sha=SHA, input_snapshot_id="snapshot")

    def test_availability_is_serialized_in_utc(self) -> None:
        signal = build_research_signals(self.rows, snapshot_acquired_at="2026-10-04T08:00:00+08:00",
            as_of="2026-10-04T08:00:00+08:00", commit_sha=SHA, input_snapshot_id="snapshot")[0]
        self.assertEqual(signal["available_at"], ACQUIRED)

    def test_schema_date_time_checker_is_enabled(self) -> None:
        self.assertIn("date-time", FormatChecker.checkers)
        self.assertFalse(FormatChecker().conforms("2026-10-04T00:00:00+08:00:30", "date-time"))

    def test_cli_hash_manifest_determinism_and_failure_atomicity(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            folder_path = Path(folder)
            input_path = folder_path / "input.csv"
            output_path = folder_path / "signals.json"
            with input_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
            args = [sys.executable, str(ROOT / "scripts/export_research_signals.py"), "--input", str(input_path), "--snapshot-acquired-at", ACQUIRED, "--as-of", ACQUIRED, "--commit-sha", SHA, "--output", str(output_path)]
            first = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_bytes = output_path.read_bytes()
            manifest_path = output_path.with_suffix(".manifest.json")
            first_manifest = manifest_path.read_bytes()
            expected_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
            signals = json.loads(first_bytes)
            manifest = json.loads(first_manifest)
            self.assertEqual(signals[0]["lineage"]["input_snapshot_id"], "sha256:" + expected_hash)
            self.assertIn(f"source_file:{input_path};sha256:{expected_hash}", signals[0]["lineage"]["inputs"])
            self.assertEqual(manifest["input_sha256"], expected_hash)
            self.assertIn("PROXY_PUBLICATION_TIME", manifest["quality_warnings"])
            self.assertEqual(len(manifest["signals"]), 3)
            self.assertEqual(subprocess.run(args, capture_output=True, text=True, cwd=ROOT).returncode, 0)
            self.assertEqual(output_path.read_bytes(), first_bytes)
            self.assertEqual(manifest_path.read_bytes(), first_manifest)
            output_path.unlink()
            manifest_path.unlink()
            bad = subprocess.run(args[:-2] + ["--commit-sha", "bad", "--output", str(output_path)], capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse(output_path.exists())
            self.assertFalse(manifest_path.exists())

    def test_cli_preflights_manifest_directory_without_writing_signals(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            directory = Path(folder)
            source = directory / "input.csv"
            output = directory / "signals.json"
            output.with_suffix(".manifest.json").mkdir()
            with source.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
            result = export_research_signals.main(["--input", str(source), "--snapshot-acquired-at", ACQUIRED, "--as-of", ACQUIRED, "--commit-sha", SHA, "--output", str(output)])
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_cli_restores_existing_pair_when_second_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            directory = Path(folder)
            source = directory / "input.csv"
            output = directory / "signals.json"
            manifest = output.with_suffix(".manifest.json")
            output.write_bytes(b"previous signals\n")
            manifest.write_bytes(b"previous manifest\n")
            with source.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
            real_replace = export_research_signals.os.replace
            calls = 0

            def fail_second_replace(source_path: object, target_path: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated manifest replacement failure")
                real_replace(source_path, target_path)

            with patch.object(export_research_signals.os, "replace", side_effect=fail_second_replace):
                result = export_research_signals.main(["--input", str(source), "--snapshot-acquired-at", ACQUIRED, "--as-of", ACQUIRED, "--commit-sha", SHA, "--output", str(output)])
            self.assertEqual(result, 1)
            self.assertEqual(output.read_bytes(), b"previous signals\n")
            self.assertEqual(manifest.read_bytes(), b"previous manifest\n")
            self.assertEqual(list(directory.glob(".*.tmp")), [])

    def test_cli_removes_new_output_when_manifest_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            directory = Path(folder)
            source = directory / "input.csv"
            output = directory / "signals.json"
            with source.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
            real_replace = export_research_signals.os.replace
            def fail_manifest(source_path: object, target_path: object) -> None:
                if Path(target_path) == output.with_suffix(".manifest.json"):
                    raise OSError("simulated manifest replacement failure")
                real_replace(source_path, target_path)
            with patch.object(export_research_signals.os, "replace", side_effect=fail_manifest):
                status = export_research_signals.main(["--input", str(source), "--snapshot-acquired-at", ACQUIRED, "--as-of", ACQUIRED, "--commit-sha", SHA, "--output", str(output)])
            self.assertEqual(status, 1)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".manifest.json").exists())
            self.assertEqual(list(directory.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
