from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core import free_evidence_connectors as connectors
from scripts import collect_free_evidence as collector


def official_payload():
    # Reduced API-JSON response from DGBAS A050106010; no download time is a release time.
    return {
        "meta": {"sender": {"id": "dgbas"}, "prepared": "2026-10-25 10:22:00"},
        "data": {
            "dataSets": [{"series": {"0:0": {"observations": {"0": [27733], "1": [47415]}}}}],
            "structure": {
                "name": "外銷訂單按主要接單貨品",
                "dimensions": {
                    "series": [
                        {"id": "fldid", "keyPosition": 0, "values": [{"id": "2", "name": "美金計價(百萬美元)"}]},
                        {"id": "code1", "keyPosition": 1, "values": [{"id": "6", "name": "電子產品"}]},
                    ],
                    "observation": [{"id": "ym", "values": [{"id": "2025-M9"}, {"id": "2026-M9"}]}],
                },
            },
        },
    }


class MoeaOfficialFallbackTests(unittest.TestCase):
    now = pd.Timestamp("2026-10-25T02:30:00Z")

    def parse(self, payload):
        parser = getattr(connectors, "parse_dgbas_export_orders_json", None)
        self.assertIsNotNone(parser, "the official JSON fallback must validate its series semantics")
        return parser(json.dumps(payload, ensure_ascii=False), source_id="moea_export_orders_electronics",
                      chain="Compute", dimension="orders_backlog", commodity_id="6",
                      collected_at=self.now, source_url="https://nstatdb.dgbas.gov.tw/example")

    def test_same_monthly_levels_and_yoy_preserve_conservative_availability(self):
        frame = self.parse(official_payload())
        evidence = collector.moea_snapshot_to_evidence(frame)
        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(evidence.iloc[0]["yoy_pct"], 70.96960300003605)
        self.assertEqual(frame.iloc[-1]["period"], "2026-09")
        self.assertTrue(frame["published_at"].eq(self.now).all())
        self.assertEqual(frame.iloc[0]["provider"], "MOEA")
        self.assertEqual(frame.iloc[0]["distributor"], "DGBAS")

    def test_query_rolls_back_to_previous_year_and_never_requests_unfinished_month(self):
        build = getattr(connectors, "dgbas_export_orders_url", None)
        self.assertIsNotNone(build)
        self.assertIn("2.9..M&startTime=1984-M1&endTime=2025-M12",
                      build("9", as_of=pd.Timestamp("2026-01-02T00:00:00Z")))
        with self.assertRaises(ValueError):
            build("1", as_of=self.now)

    def test_wrong_currency_commodity_and_table_fail_closed(self):
        for field in ("currency", "commodity", "table"):
            with self.subTest(field=field):
                a = official_payload()
                if field == "table":
                    a["data"]["structure"]["name"] = "其他統計表"
                else:
                    dim = a["data"]["structure"]["dimensions"]["series"][0 if field == "currency" else 1]
                    dim["values"][0] = {"id": "1", "name": "新臺幣計價(億元)" if field == "currency" else "合計"}
                with self.assertRaises(ValueError):
                    self.parse(a)

    def test_unreleased_zero_annual_period_and_nonfinite_values_are_rejected(self):
        cases = []
        for value in (0, -1, None, float("nan"), float("inf")):
            a = official_payload()
            a["data"]["dataSets"][0]["series"]["0:0"]["observations"]["1"] = [value]
            cases.append(a)
        a = official_payload()
        a["data"]["structure"]["dimensions"]["observation"][0]["values"][1]["id"] = "2026"
        cases.append(a)
        a = official_payload()
        a["data"]["dataSets"][0]["series"]["0:0"]["observations"]["0"] = [0]
        cases.append(a)
        for a in cases:
            with self.subTest(payload=a), self.assertRaises(ValueError):
                self.parse(a)

    def test_sparse_or_extra_series_cannot_be_counted_as_healthy(self):
        for case in ("empty", "extra", "bad_index", "duplicate_month"):
            a = official_payload()
            series = a["data"]["dataSets"][0]["series"]
            if case == "empty":
                series["0:0"]["observations"] = {}
            elif case == "extra":
                series["0:1"] = copy.deepcopy(series["0:0"])
            elif case == "bad_index":
                series["0:0"]["observations"]["9"] = [123]
            else:
                a["data"]["structure"]["dimensions"]["observation"][0]["values"][1]["id"] = "2025-M9"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.parse(a)

    def collect(self, fetch):
        cfg = json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        source = next(x for x in cfg["sources"] if x["source_id"] == "moea_export_orders_electronics")
        cfg["sources"] = [source]
        # Keep fixture paths inside the repo, like the production raw trace paths.
        with tempfile.TemporaryDirectory(dir=collector.ROOT) as tmp:
            root = Path(tmp)
            config = root / "sources.json"
            config.write_text(json.dumps(cfg), encoding="utf-8")
            with patch.object(collector, "fetch_bytes", side_effect=fetch), patch.object(collector, "utc_now", return_value=self.now):
                return collector.collect_all(config_path=config, persistent_root=root / "raw", artifacts_dir=root / "artifacts")

    def test_primary_403_uses_verified_official_series_and_records_failure(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if "data.gov.tw" in url:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return connectors.FetchResult(url, self.now, json.dumps(official_payload()).encode())
        evidence, status = self.collect(fetch)
        self.assertEqual(status["sources_ok"], 1)
        self.assertEqual(len(evidence), 1)
        result = status["sources"][0]
        self.assertEqual(result["fetch_mode"], "OFFICIAL_FALLBACK")
        self.assertIn("403", result["primary_error"])
        self.assertIn("nstatdb.dgbas.gov.tw", result["source_url"])
        self.assertEqual(result["distributor"], "DGBAS")
        self.assertEqual(evidence.iloc[0]["source_fetch_mode"], "OFFICIAL_FALLBACK")
        self.assertEqual(evidence.iloc[0]["source_distributor"], "DGBAS")
        self.assertEqual(len(evidence.iloc[0]["raw_sha256"]), 64)
        self.assertEqual(evidence.iloc[0]["published_at"], self.now)
        self.assertTrue(evidence.iloc[0]["raw_snapshot_path"].endswith(".json"))
        # End at the last completed month; the API can invent a zero for the current month.
        self.assertIn("endTime=2026-M9", calls[-1])

    def test_csv_403_also_falls_back_and_keeps_the_failed_resource_url(self):
        def fetch(url):
            if "data.gov.tw" in url:
                a = {"distribution": [{"resourceDownloadUrl": "https://www.moea.gov.tw/official.csv"}]}
                return connectors.FetchResult(url, self.now, json.dumps(a).encode())
            if "moea.gov.tw" in url:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return connectors.FetchResult(url, self.now, json.dumps(official_payload()).encode())
        evidence, status = self.collect(fetch)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(status["sources"][0]["primary_source_url"], "https://www.moea.gov.tw/official.csv")

    def test_healthy_csv_keeps_primary_transport(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if "data.gov.tw" in url:
                raw = json.dumps({"distribution": [{"resourceDownloadUrl": "https://www.moea.gov.tw/official.csv"}]}).encode()
            else:
                raw = "統計項目,資料期,統計值,計量單位\n電子產品,114年9月,27733,百萬美元\n電子產品,115年9月,47415,百萬美元\n".encode()
            return connectors.FetchResult(url, self.now, raw)
        evidence, status = self.collect(fetch)
        self.assertEqual(status["sources_ok"], 1)
        self.assertEqual(status["sources"][0]["fetch_mode"], "PRIMARY")
        self.assertEqual(evidence.iloc[0]["source_distributor"], "MOEA")
        self.assertFalse(any("dgbas" in u for u in calls))

    def test_unavailable_latest_month_requeries_one_month_back_with_explicit_period(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if "data.gov.tw" in url:
                raise RuntimeError("403 blocked")
            a = official_payload()
            if "endTime=2026-M9" in url:
                a["data"]["dataSets"][0]["series"]["0:0"]["observations"]["1"] = [0]
            else:
                self.assertIn("endTime=2026-M8", url)
                a["data"]["structure"]["dimensions"]["observation"][0]["values"] = [{"id": "2025-M8"}, {"id": "2026-M8"}]
                a["data"]["dataSets"][0]["series"]["0:0"]["observations"] = {"0": [24880], "1": [45755]}
            return connectors.FetchResult(url, self.now, json.dumps(a).encode())
        evidence, status = self.collect(fetch)
        self.assertEqual(status["sources_ok"], 1)
        self.assertEqual(evidence.iloc[0]["period_date"], "2026-08")
        self.assertAlmostEqual(evidence.iloc[0]["yoy_pct"], (45755/24880-1)*100)
        self.assertEqual(status["sources"][0]["unavailable_period"], "2026-09")
        self.assertEqual(status["sources"][0]["latest_observation_period"], "2026-08")
        self.assertEqual(len(calls), 3)

    def test_query_timestamp_changes_keep_first_seen_but_archive_actual_new_raw_bytes(self):
        cfg = json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        cfg["sources"] = [next(s for s in cfg["sources"] if s["source_id"] == "moea_export_orders_electronics")]
        with tempfile.TemporaryDirectory(dir=collector.ROOT) as tmp:
            root = Path(tmp)
            config = root / "sources.json"
            config.write_text(json.dumps(cfg), encoding="utf-8")
            observations = []
            for day in (0, 1):
                now = self.now + pd.Timedelta(days=day)
                a = official_payload()
                a["meta"]["prepared"] = now.isoformat()
                def fetch(url):
                    if "data.gov.tw" in url:
                        raise RuntimeError("403 blocked")
                    return connectors.FetchResult(url, now, json.dumps(a).encode())
                with patch.object(collector, "fetch_bytes", side_effect=fetch), patch.object(collector, "utc_now", return_value=now):
                    evidence, status = collector.collect_all(config_path=config, persistent_root=root / "raw", artifacts_dir=root / "artifacts")
                observations.append((evidence, status["sources"][0]))
            first, second = observations
            self.assertEqual(second[0].iloc[0]["published_at"], self.now)
            self.assertNotEqual(first[1]["sha256"], second[1]["sha256"])
            self.assertNotEqual(first[1]["persistent_path"], second[1]["persistent_path"])
            self.assertEqual(second[1]["fetch_collected_at"], now.isoformat())
            self.assertEqual(second[1]["canonical_available_at"], self.now.isoformat())
            import hashlib
            raw = collector.ROOT / second[1]["persistent_path"]
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), second[1]["sha256"])

    def test_switching_transport_preserves_first_seen_but_value_revisions_advance_it(self):
        cfg = json.loads(Path("data/free_evidence_sources.json").read_text(encoding="utf-8"))
        cfg["sources"] = [next(s for s in cfg["sources"] if s["source_id"] == "moea_export_orders_electronics")]
        with tempfile.TemporaryDirectory(dir=collector.ROOT) as tmp:
            root = Path(tmp)
            config = root / "sources.json"
            config.write_text(json.dumps(cfg), encoding="utf-8")
            results = []
            for day in (0, 1, 2):
                now = self.now + pd.Timedelta(days=day)
                def fetch(url):
                    if day == 0:
                        if "data.gov.tw" in url:
                            raw = json.dumps({"distribution": [{"resourceDownloadUrl": "https://www.moea.gov.tw/official.csv"}]}).encode()
                        else:
                            raw = "統計項目,資料期,統計值,計量單位\n外銷訂單金額_美元,11409,27733,百萬美元\n外銷訂單金額_美元,11509,47415,百萬美元\n".encode()
                    else:
                        if "data.gov.tw" in url:
                            raise RuntimeError("403 blocked")
                        a = official_payload()
                        if day == 2:
                            a["data"]["dataSets"][0]["series"]["0:0"]["observations"]["1"] = [47416]
                        raw = json.dumps(a).encode()
                    return connectors.FetchResult(url, now, raw)
                with patch.object(collector, "fetch_bytes", side_effect=fetch), patch.object(collector, "utc_now", return_value=now):
                    evidence, status = collector.collect_all(config_path=config, persistent_root=root / "raw", artifacts_dir=root / "artifacts")
                results.append((evidence.iloc[0], status["sources"][0]))
            self.assertEqual(results[0][1]["fetch_mode"], "PRIMARY")
            self.assertEqual(results[1][1]["fetch_mode"], "OFFICIAL_FALLBACK")
            self.assertEqual(results[1][0]["published_at"], self.now)
            self.assertEqual(results[0][1]["observation_sha256"], results[1][1]["observation_sha256"])
            self.assertNotEqual(results[1][1]["observation_sha256"], results[2][1]["observation_sha256"])
            self.assertEqual(results[2][0]["published_at"], now)

    def test_failed_or_wrong_fallback_remains_error_without_cached_promotion(self):
        for response in (None, {"html": "not statistics"}, official_payload()):
            if response is not None and "data" in response:
                response["data"]["dataSets"][0]["series"]["0:0"]["observations"] = {"1": [47415]}
            def fetch(url):
                if "data.gov.tw" in url or response is None:
                    raise RuntimeError("403 blocked")
                return connectors.FetchResult(url, self.now, json.dumps(response).encode())
            evidence, status = self.collect(fetch)
            self.assertEqual(status["sources_ok"], 0)
            self.assertEqual(status["sources"][0]["status"], "error")
            self.assertIn("403", status["sources"][0]["primary_error"])
            self.assertTrue(evidence.empty)


if __name__ == "__main__":
    unittest.main()
