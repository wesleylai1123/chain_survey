"""Company-specific, descriptive Revenue -> GM audit with explicit knowledge bounds.

This module does not identify ABF-only economics from company financial statements.
Its fixed comparisons and holdouts are references, never a coefficient search.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from scipy.stats import rankdata


COMPANIES = ("3037.TW", "3189.TW", "8046.TW")
FEATURES = ("monthly_revenue_3m_yoy", "revenue_yoy")
TARGETS = ("gross_margin_qoq", "gross_margin_yoy_delta")
SCENARIOS = ("UPSIDE", "DOWNSIDE")
LAGS = (0, 1, 2)
FOLD_BOUNDS = ((0.50, 0.65), (0.65, 0.80), (0.80, 1.00))
_VALUE_MATCHES = {"MATCH", "ROUNDED_MATCH"}
_TIME_FIELDS = (
    "filing_published_at", "snapshot_acquired_at", "available_at", "acquired_at",
    "financial_basis_verification_available_at", "financial_evidence_acquired_at",
    "signal_generated_at", "financial_release_date",
)
_URL_FIELDS = ("fundamental_source_url", "filing_source_url", "primary_financial_source_url")
_MONTHLY_TIME_FIELDS = (
    "monthly_source_release_date", "monthly_revenue_available_at", "monthly_revenue_acquired_at",
    "monthly_revenue_snapshot_acquired_at", "monthly_revenue_verification_available_at",
    "monthly_revenue_signal_generated_at",
)
_MONTHLY_ACCOUNTING_BASIS = "CONSOLIDATED_MONTHLY_REVENUE"


def _present(value) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _time(value, *, end_of_day=False):
    if not _present(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    stamp = pd.Timestamp(parsed)
    date_only = len(str(value).strip()) == 10
    if stamp.tzinfo is None:
        if not date_only:
            return None
        stamp = stamp.tz_localize("Asia/Taipei")
    if end_of_day and date_only:
        stamp += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return stamp.tz_convert("UTC")


def _iso(stamp):
    return stamp.isoformat() if stamp is not None else None


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _true(value) -> bool:
    return isinstance(value, (bool, np.bool_)) and bool(value) or (
        isinstance(value, str) and value.strip().lower() == "true"
    )


def _urls(row) -> list[str]:
    return sorted({str(row[key]).strip() for key in _URL_FIELDS if _present(row.get(key))
                   and urlparse(str(row[key])).scheme in {"https", "http"}
                   and urlparse(str(row[key])).netloc})


def _prepare(panel, cutoff):
    companies = {company: {} for company in COMPANIES}
    excluded = {}
    duplicates = set()
    for record in panel.to_dict("records"):
        identifier = str(record.get("ticker", record.get("stock_id", "")))
        company = next((c for c in COMPANIES if identifier in {c, c[:4]}), None)
        if company is None:
            continue
        date = pd.to_datetime(record.get("report_date"), errors="coerce")
        if pd.isna(date):
            excluded["INVALID_OBSERVATION_DATE"] = excluded.get("INVALID_OBSERVATION_DATE", 0) + 1
            continue
        date = pd.Timestamp(date)
        if date.tzinfo is not None:
            date = date.tz_convert("Asia/Taipei").tz_localize(None)
        quarter = pd.Period(date, freq="Q")
        if date.normalize() != quarter.end_time.normalize():
            excluded["NON_QUARTER_END_OBSERVATION"] = excluded.get("NON_QUARTER_END_OBSERVATION", 0) + 1
            continue
        available = _time(record.get("available_date"), end_of_day=True)
        bounds = [available] if available is not None else []
        invalid = available is None
        for field in _TIME_FIELDS:
            if _present(record.get(field)):
                stamp = _time(record[field], end_of_day=True)
                invalid |= stamp is None
                if stamp is not None:
                    bounds.append(stamp)
        if invalid:
            excluded["MISSING_OR_INVALID_KNOWLEDGE_TIME"] = excluded.get("MISSING_OR_INVALID_KNOWLEDGE_TIME", 0) + 1
            continue
        known = max(bounds)
        if known < _time(str(quarter.end_time.date()), end_of_day=True):
            excluded["KNOWLEDGE_BEFORE_OBSERVATION_END"] = excluded.get("KNOWLEDGE_BEFORE_OBSERVATION_END", 0) + 1
            continue
        if known > cutoff:
            excluded["FUTURE_KNOWLEDGE"] = excluded.get("FUTURE_KNOWLEDGE", 0) + 1
            continue
        key = company, quarter
        if quarter in companies[company] or key in duplicates:
            # Neither an arbitrary input order nor an unresolved vintage wins.
            duplicates.add(key)
            companies[company].pop(quarter, None)
            excluded["DUPLICATE_QUARTER"] = excluded.get("DUPLICATE_QUARTER", 0) + 1
            continue
        release = _time(record.get("financial_release_date"), end_of_day=True)
        if "financial_release_date" not in record:
            release = _time(record.get("filing_published_at"))
        record.update({
            "_id": f"{company}:{quarter}", "_quarter": quarter, "_known": known,
            "_release": release, "_urls": _urls(record),
            "_basis_verified": record.get("accounting_basis") == "STANDALONE_QUARTER"
            and record.get("financial_value_verification") in _VALUE_MATCHES
            and _present(record.get("financial_evidence_id"))
            and str(record.get("primary_financial_source_url", "")).strip() in _urls(record),
        })
        record["_summary"] = _dependency_summary(record)
        companies[company][quarter] = record
    return companies, excluded


def _gross_margin(record):
    revenue, profit = _number(record.get("revenue")), _number(record.get("gross_profit"))
    if revenue is not None and profit is not None and revenue != 0:
        return profit / revenue
    return _number(record.get("gross_margin"))


def _values(feature, target, feature_row, target_row, feature_base, target_base):
    """Use raw calendar endpoints when available; label unverified fallbacks."""
    x = _number(feature_row.get(feature))
    feature_verified = False
    if feature == "revenue_yoy":
        revenue = _number(feature_row.get("revenue"))
        previous = _number(feature_base.get("revenue"))
        if revenue is not None and previous is not None and previous != 0:
            x, feature_verified = revenue / previous - 1, True
    current, previous = _gross_margin(target_row), _gross_margin(target_base)
    target_verified = current is not None and previous is not None
    y = current - previous if target_verified else _number(target_row.get(target))
    feature_source = "PROVIDED_MONTHLY_FEATURE" if feature == "monthly_revenue_3m_yoy" else (
        "RAW_REVENUE_CALENDAR_ENDPOINTS" if feature_verified else "PRECOMPUTED_UNVERIFIED"
    )
    target_source = "RAW_GROSS_MARGIN_ENDPOINTS" if target_verified else "PRECOMPUTED_UNVERIFIED"
    return x, y, feature_verified, target_verified, feature_source, target_source


def _max_release(dependencies):
    releases = [r["_release"] for r in dependencies]
    return max(releases) if releases and all(r is not None for r in releases) else None


def _dependency_summary(record):
    return {
        "dependency_id": record["_id"], "observation_date": str(record["_quarter"].end_time.date()),
        "known_at": _iso(record["_known"]), "release_date": _iso(record["_release"]),
        "source_urls": record["_urls"],
        **{field: str(record[field]).strip() if _present(record.get(field)) else None for field in _URL_FIELDS},
        "available_at": _iso(_time(record.get("available_date"), end_of_day=True)),
        "declared_available_at": _iso(_time(record.get("available_at"), end_of_day=True)),
        **{field: _iso(_time(record.get(field), end_of_day=True)) for field in _TIME_FIELDS if field != "available_at"},
        "accounting_basis": str(record["accounting_basis"]) if _present(record.get("accounting_basis")) else "UNKNOWN",
        "financial_value_verification": str(record["financial_value_verification"]) if _present(record.get("financial_value_verification")) else "UNVERIFIED",
        "financial_evidence_id": record.get("financial_evidence_id") if _present(record.get("financial_evidence_id")) else None,
        "financial_evidence_sha256": record.get("financial_evidence_sha256") if _present(record.get("financial_evidence_sha256")) else None,
        "pit_exact": _true(record.get("financial_pit_exact")), "is_proxy": True,
    }


def _financial_provenance(dependencies, values_verified):
    basis_verified = values_verified and all(r["_basis_verified"] for r in dependencies)
    return {
        "known": max(r["_known"] for r in dependencies), "release": _max_release(dependencies),
        "source_urls": sorted({url for r in dependencies for url in r["_urls"]}),
        "source_verified": all(bool(r["_urls"]) for r in dependencies),
        "accounting_basis": "STANDALONE_QUARTER" if basis_verified else "UNKNOWN",
        "accounting_verified": basis_verified,
        "pit_exact": values_verified and all(_true(r.get("financial_pit_exact")) for r in dependencies),
        "value_verification": "RAW_CALENDAR_ENDPOINTS" if values_verified else "PRECOMPUTED_UNVERIFIED",
        "dependencies": [r["_summary"] for r in dependencies],
    }


def _monthly_provenance(record, company, quarter, cutoff):
    """Audit provided monthly growth independently from quarterly financial proof.

    The quarterly panel has no month-vintage records. An independently reconciled
    monthly input must supply its own source, evidence ID, value match, accounting
    scope, publication, acquisition and verification bounds. Financial flags never
    verify those facts. Missing monthly proof leaves a descriptive input reference.
    """
    bounds, times = [record["_known"]], {}
    for field in (*_MONTHLY_TIME_FIELDS, "monthly_revenue_available_date"):
        stamp = _time(record.get(field), end_of_day=True)
        if _present(record.get(field)) and (stamp is None or stamp > cutoff):
            return None
        times[field] = stamp
        if stamp is not None:
            bounds.append(stamp)
    known = max(bounds)
    monthly_url = str(record.get("monthly_revenue_source_url", "")).strip()
    parsed = urlparse(monthly_url)
    urls = [monthly_url] if parsed.scheme in {"http", "https"} and parsed.netloc else []
    acquired = max((times[field] for field in ("monthly_revenue_acquired_at", "monthly_revenue_snapshot_acquired_at")
                    if times[field] is not None), default=None)
    evidence_id = record.get("monthly_revenue_evidence_id")
    verification = record.get("monthly_revenue_value_verification")
    value_verified = bool(verification in _VALUE_MATCHES and _present(evidence_id) and urls
                          and acquired is not None and times["monthly_revenue_verification_available_at"] is not None)
    basis_verified = value_verified and record.get("monthly_revenue_accounting_basis") == _MONTHLY_ACCOUNTING_BASIS
    release = times["monthly_source_release_date"]
    pit_exact = bool(value_verified and release is not None and _true(record.get("monthly_revenue_pit_exact")))
    dependency = {
        "dependency_id": f"{company}:MONTHLY_REVENUE_3M:{quarter}",
        "dependency_type": "MONTHLY_REVENUE_FEATURE", "observation_date": str(quarter.end_time.date()),
        "known_at": _iso(known), "release_date": _iso(release), "source_urls": urls,
        "monthly_revenue_source_url": urls[0] if urls else None,
        "provider_reference_url": str(record["fundamental_source_url"]) if _present(record.get("fundamental_source_url")) else None,
        "snapshot_acquired_at": _iso(_time(record.get("snapshot_acquired_at"), end_of_day=True)),
        **{field: _iso(stamp) for field, stamp in times.items()},
        "accounting_basis": _MONTHLY_ACCOUNTING_BASIS if basis_verified else "UNKNOWN",
        "value_verification": str(verification) if _present(verification) else "UNVERIFIED",
        "evidence_id": str(evidence_id) if _present(evidence_id) else None,
        "pit_exact": pit_exact, "is_proxy": True, "value_source": "PROVIDED_MONTHLY_FEATURE",
    }
    return {
        "known": known, "release": release, "source_urls": urls, "source_verified": bool(urls),
        "accounting_basis": dependency["accounting_basis"], "accounting_verified": basis_verified,
        "pit_exact": pit_exact, "value_verification": dependency["value_verification"],
        "dependencies": [dependency],
    }


def _align(raw, company, feature, target, lag, cutoff):
    result = []
    for fq in sorted(raw):
        tq = fq + lag
        target_prior = tq - (1 if target == "gross_margin_qoq" else 4)
        feature_prior = fq - 4 if feature == "revenue_yoy" else fq
        # Continuity is conservative: never silently bridge a missing quarter.
        if any(q not in raw for q in pd.period_range(min(feature_prior, target_prior), tq, freq="Q")):
            continue
        fdeps = [raw[q] for q in sorted({fq, feature_prior})]
        tdeps = [raw[q] for q in sorted({tq, target_prior})]
        x, y, feature_values_verified, target_values_verified, feature_source, target_source = _values(
            feature, target, raw[fq], raw[tq], raw[feature_prior], raw[target_prior]
        )
        if x is None or y is None:
            continue
        feature_proof = (_monthly_provenance(raw[fq], company, fq, cutoff) if feature == "monthly_revenue_3m_yoy"
                         else _financial_provenance(fdeps, feature_values_verified))
        if feature_proof is None:
            continue
        target_proof = _financial_provenance(tdeps, target_values_verified)
        fknown, tknown = feature_proof["known"], target_proof["known"]
        dependencies = {r["dependency_id"]: r for r in feature_proof["dependencies"] + target_proof["dependencies"]}
        values_verified = feature_values_verified and target_values_verified
        basis = "STANDALONE_QUARTER" if feature_proof["accounting_verified"] and target_proof["accounting_verified"] else "UNKNOWN"
        source_urls = sorted(set(feature_proof["source_urls"] + target_proof["source_urls"]))
        feature_date, target_date = str(fq.end_time.date()), str(tq.end_time.date())
        result.append({
            "company": company, "product": "ABF", "feature_period": str(fq), "target_period": str(tq),
            "feature_observation_date": feature_date, "target_observation_date": target_date,
            "feature_report_date": feature_date, "target_report_date": target_date,
            "feature_release_date": _iso(feature_proof["release"]), "target_release_date": _iso(target_proof["release"]),
            "feature_available_at": _iso(fknown), "target_available_at": _iso(tknown),
            "feature_signal_generated_at": _iso(fknown), "target_signal_generated_at": _iso(tknown),
            "feature_known_at": _iso(fknown), "target_known_at": _iso(tknown),
            "signal_time_basis": "RECONSTRUCTED_KNOWLEDGE_BOUND",
            "x": x * 100, "y": y * 100, "x_ratio": x, "y_ratio": y,
            "feature_value_source": feature_source, "target_value_source": target_source,
            "feature_value_verification": feature_proof["value_verification"],
            "target_value_verification": target_proof["value_verification"],
            "value_verification": (
                "PROVIDED_MONTHLY_FEATURE_WITH_RAW_GM_ENDPOINTS" if target_values_verified and feature == "monthly_revenue_3m_yoy"
                else "RAW_CALENDAR_ENDPOINTS" if values_verified else "PRECOMPUTED_UNVERIFIED"
            ),
            "dependency_ids": sorted(dependencies),
            "feature_dependency_ids": sorted(r["dependency_id"] for r in feature_proof["dependencies"]),
            "target_dependency_ids": sorted(r["dependency_id"] for r in target_proof["dependencies"]),
            "dependency_rows": [dependencies[key] for key in sorted(dependencies)],
            "feature_source_urls": feature_proof["source_urls"], "target_source_urls": target_proof["source_urls"],
            "feature_source_verified": feature_proof["source_verified"], "target_source_verified": target_proof["source_verified"],
            "feature_accounting_basis": feature_proof["accounting_basis"], "target_accounting_basis": target_proof["accounting_basis"],
            "feature_accounting_verified": feature_proof["accounting_verified"], "target_accounting_verified": target_proof["accounting_verified"],
            "feature_pit_exact": feature_proof["pit_exact"], "target_pit_exact": target_proof["pit_exact"],
            "source_urls": source_urls, "source_verified": feature_proof["source_verified"] and target_proof["source_verified"],
            "accounting_basis": basis, "accounting_verified": basis != "UNKNOWN",
            "pit_exact": feature_proof["pit_exact"] and target_proof["pit_exact"],
            "is_proxy": True, "source_scope": "COMPANY_TOTAL", "evidence_status": "DERIVED",
            "_fq": fq, "_tq": tq, "_fknown": fknown, "_tknown": tknown,
            "_early": lag > 0 and fknown < _time(target_date, end_of_day=True),
        })
    return result


def _correlation(x, y):
    if len(x) < 3 or _constant(x) or _constant(y):
        return None
    rx, ry = rankdata(x), rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    value = float(np.dot(rx, ry) / np.sqrt(np.dot(rx, rx) * np.dot(ry, ry)))
    return min(1.0, max(-1.0, value))


def _slope(x, y):
    if len(x) < 2 or _constant(x):
        return None
    if _constant(y):
        return 0.0
    centered = x - x.mean()
    return float(np.dot(centered, y - y.mean()) / np.dot(centered, centered))


def _constant(values):
    # GP / revenue arithmetic must not turn a constant margin into ranked noise.
    return len(values) == 0 or np.ptp(values) <= 1e-12 * max(1.0, float(np.max(np.abs(values))))


def _blocks(samples):
    blocks, current = [], []
    previous = None
    for index, sample in enumerate(samples):
        quarter = sample["_fq"].ordinal
        if current and (quarter != previous + 1 or len(current) == 2):
            blocks.append(current)
            current = []
        current.append(index)
        previous = quarter
    if current:
        blocks.append(current)
    return blocks


def _uncertainty(samples, correlation, iterations, seed):
    empty = dict(bootstrap_ci_low=None, bootstrap_ci_high=None, beta_ci_low=None,
                 beta_ci_high=None, permutation_p=None)
    if len(samples) < 6 or correlation is None:
        return empty
    x, y = np.array([s["x"] for s in samples]), np.array([s["y"] for s in samples])
    blocks = _blocks(samples)
    rng = np.random.default_rng(seed)
    correlations, slopes, exceedances = [], [], 0
    for _ in range(iterations):
        # Every selected block is bounded by a calendar/conditional-sample gap.
        selected = []
        while len(selected) < len(samples):
            selected.extend(blocks[int(rng.integers(len(blocks)))])
        indices = np.array(selected[:len(samples)])
        corr, beta = _correlation(x[indices], y[indices]), _slope(x[indices], y[indices])
        if corr is not None:
            correlations.append(corr)
        if beta is not None:
            slopes.append(beta)
        permutation = np.concatenate([blocks[int(i)] for i in rng.permutation(len(blocks))])
        shuffled = _correlation(x, y[permutation])
        if shuffled is not None and abs(shuffled) >= abs(correlation) - 1e-12:
            exceedances += 1
    return {
        "bootstrap_ci_low": float(np.quantile(correlations, 0.025)) if correlations else None,
        "bootstrap_ci_high": float(np.quantile(correlations, 0.975)) if correlations else None,
        "beta_ci_low": float(np.quantile(slopes, 0.025)) if slopes else None,
        "beta_ci_high": float(np.quantile(slopes, 0.975)) if slopes else None,
        "permutation_p": (1 + exceedances) / (1 + iterations),
    }


def _side(samples, scenario):
    return [s for s in samples if (s["x"] > 0 if scenario == "UPSIDE" else s["x"] < 0)]


def _folds(unconditional, scenario):
    folds = []
    for index, (start, stop) in enumerate(FOLD_BOUNDS, 1):
        left, right = int(len(unconditional) * start), int(len(unconditional) * stop)
        test_all = unconditional[left:right]
        first_known = min((s["_fknown"] for s in test_all), default=None)
        train = _side([s for s in unconditional[:left] if first_known is not None
                       and max(s["_fknown"], s["_tknown"]) < first_known], scenario)
        test = _side(test_all, scenario)
        tx, ty = np.array([s["x"] for s in train]), np.array([s["y"] for s in train])
        vx, vy = np.array([s["x"] for s in test]), np.array([s["y"] for s in test])
        reasons = []
        if len(train) < 6:
            reasons.append("INSUFFICIENT_KNOWN_TRAINING_LABELS")
        if len(test) < 3:
            reasons.append("INSUFFICIENT_TEST_OBSERVATIONS")
        train_corr, test_corr = _correlation(tx, ty), _correlation(vx, vy)
        if len(train) >= 6 and train_corr is None:
            reasons.append("CONSTANT_TRAINING_DATA")
        if len(test) >= 3 and test_corr is None:
            reasons.append("CONSTANT_TEST_DATA")
        valid = not reasons
        beta = _slope(tx, ty) if valid else None
        predicted_corr = _correlation(vx * beta, vy) if valid else None
        folds.append({
            "fold": index, "train_fraction": start, "test_end_fraction": stop,
            "test_start_period": test_all[0]["feature_period"] if test_all else None,
            "test_end_period": test_all[-1]["feature_period"] if test_all else None,
            "train_sample_size": len(train), "test_sample_size": len(test),
            "train_last_feature_known_at": _iso(max((s["_fknown"] for s in train), default=None)),
            "train_last_label_known_at": _iso(max((s["_tknown"] for s in train), default=None)),
            "test_first_feature_known_at": _iso(first_known),
            "train_beta": beta, "spearman": test_corr if valid else None,
            "prediction_spearman": predicted_corr, "valid": valid,
            "direction_consistent": bool(valid and beta > 0 and test_corr > 0),
            "rejection_reasons": reasons,
        })
    return folds


def _comparison(company, scenario, feature, target, lag, unconditional, iterations):
    identifier = f"{company}|ABF|{scenario}|{feature}|{target}|L{lag}"
    samples = _side(unconditional, scenario)
    x, y = np.array([s["x"] for s in samples]), np.array([s["y"] for s in samples])
    corr, beta = _correlation(x, y), _slope(x, y)
    seed = int.from_bytes(hashlib.sha256(identifier.encode("utf-8")).digest()[:8], "big")
    uncertainty = _uncertainty(samples, corr, iterations, seed)
    folds = _folds(unconditional, scenario)
    valid = [f for f in folds if f["valid"]]
    sign_stability = sum(f["direction_consistent"] for f in valid) / len(valid) if valid else None
    basis = "STANDALONE_QUARTER" if samples and all(s["accounting_verified"] for s in samples) else "UNKNOWN"
    return {
        "comparison_id": identifier, "company": company, "product": "ABF", "scenario": scenario,
        "feature": feature, "target": target, "lag_quarters": lag,
        "timing_class": "COINCIDENT" if lag == 0 else "LEADING_CANDIDATE", "expected_direction": 1,
        "data_status": "DESCRIPTIVE_PROXY_ONLY" if samples else "UNAVAILABLE",
        "sample_size": len(samples), "unconditional_sample_size": len(unconditional),
        "spearman": corr, "descriptive_beta": beta,
        "descriptive_beta_status": "ESTIMATED" if beta is not None else "UNKNOWN",
        "descriptive_beta_units": "GM_CHANGE_PP_PER_REVENUE_GROWTH_PP",
        "x_units": "REVENUE_GROWTH_PP", "y_units": "GM_CHANGE_PP",
        **uncertainty, "fdr_q": 1.0, "fdr_family_size": 36, "fdr_family": scenario,
        "fdr_input_p": uncertainty["permutation_p"] if uncertainty["permutation_p"] is not None else 1.0,
        "cross_company_sign_share": 0.0,
        "oos_spearman": float(np.mean([f["spearman"] for f in valid])) if valid else None,
        "oos_sign_stability": sign_stability, "oos_folds": folds,
        "gates": {}, "eligibility": "reject", "forecast_beta": None, "rejection_reasons": [],
        "sample_rows": [{k: v for k, v in sample.items() if not k.startswith("_")} for sample in samples],
        "source_urls": sorted({url for sample in samples for url in sample["source_urls"]}),
        "accounting_basis": basis, "pit_exact": bool(samples and all(s["pit_exact"] for s in samples)),
        "is_proxy": True, "source_scope": "COMPANY_TOTAL", "evidence_status": "DERIVED" if samples else "UNKNOWN",
        "resampling_blocks": [[samples[i]["feature_period"] for i in block] for block in _blocks(samples)],
        "_early": bool(samples and all(s["_early"] for s in samples)),
    }


def _finish(comparisons):
    for scenario in SCENARIOS:
        family = [r for r in comparisons if r["scenario"] == scenario]
        order = sorted(range(len(family)), key=lambda i: family[i]["fdr_input_p"])
        running = 1.0
        for rank in range(len(order), 0, -1):
            row = family[order[rank - 1]]
            running = min(running, row["fdr_input_p"] * 36 / rank)
            row["fdr_q"] = min(1.0, running)
    for row in comparisons:
        peers = [peer for peer in comparisons if all(peer[key] == row[key]
                 for key in ("scenario", "feature", "target", "lag_quarters"))]
        row["cross_company_sign_share"] = sum(peer["spearman"] is not None and peer["spearman"] > 0 for peer in peers) / 3
        ci_low, ci_high = row["bootstrap_ci_low"], row["bootstrap_ci_high"]
        valid_folds = sum(fold["valid"] for fold in row["oos_folds"])
        gates = {
            "minimum_samples": row["sample_size"] >= 10,
            "expected_direction": row["spearman"] is not None and row["spearman"] > 0,
            "bootstrap_excludes_zero": ci_low is not None and ci_high is not None and (ci_low > 0 or ci_high < 0),
            "permutation": row["permutation_p"] is not None and row["permutation_p"] <= 0.10,
            "fdr": row["fdr_q"] <= 0.10,
            "cross_company_sign": row["cross_company_sign_share"] >= 2 / 3,
            "oos_stability": valid_folds >= 2 and row["oos_sign_stability"] is not None and row["oos_sign_stability"] >= 2 / 3,
            "source": bool(row["sample_rows"] and all(s["source_verified"] for s in row["sample_rows"])),
            "accounting": row["accounting_basis"] == "STANDALONE_QUARTER",
            "pit": row["pit_exact"], "leading_availability": row.pop("_early"),
            "product_attribution": False,
        }
        row["gates"] = gates
        row["rejection_reasons"] = [f"GATE_FAILED:{key}" for key, passed in gates.items() if not passed] + ["COMPANY_TOTAL_PROXY"]
        row["eligibility"] = "support-only" if all(passed for key, passed in gates.items() if key != "product_attribution") else "reject"


def validate_margin_transmission(panel: pd.DataFrame, *, as_of: str, iterations: int = 999) -> dict:
    """Audit the complete predeclared 72-comparison family without choosing winners.

    All input growth and margin ratios are converted to percentage points. A
    date-only cutoff includes the entire Taiwan calendar day. Unresolved or
    future input knowledge is excluded rather than backdated to an old filing.
    """
    cutoff = _time(as_of, end_of_day=True)
    if cutoff is None:
        raise ValueError("as_of must be a valid date or timestamp")
    if isinstance(iterations, bool) or not isinstance(iterations, (int, np.integer)) or iterations < 19:
        raise ValueError("iterations must be an integer of at least 19")
    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel must be a pandas DataFrame")
    companies, excluded = _prepare(panel, cutoff)
    comparisons = []
    for company in COMPANIES:
        for feature in FEATURES:
            for target in TARGETS:
                for lag in LAGS:
                    unconditional = _align(companies[company], company, feature, target, lag, cutoff)
                    for scenario in SCENARIOS:
                        comparisons.append(_comparison(company, scenario, feature, target, lag, unconditional, int(iterations)))
    _finish(comparisons)
    usable = sum(len(rows) for rows in companies.values())
    relevant_count = sum(str(row.get("ticker", row.get("stock_id", ""))) in {*COMPANIES, *(c[:4] for c in COMPANIES)} for row in panel.to_dict("records"))
    return {
        "contract": "ABFMarginValidationV1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of, "comparisons": comparisons,
        "policy": {
            "companies": list(COMPANIES), "features": list(FEATURES), "targets": list(TARGETS),
            "lags": list(LAGS), "scenarios": list(SCENARIOS), "hypotheses_per_side": 36,
            "missing_p_value": 1.0, "expected_direction": 1, "minimum_side_samples": 10,
            "fold_bounds": [list(bound) for bound in FOLD_BOUNDS], "minimum_train_samples": 6,
            "minimum_test_samples": 3, "minimum_valid_folds": 2,
            "minimum_direction_share": 2 / 3, "permutation_alpha": 0.10, "fdr_alpha": 0.10,
            "resampling_iterations": int(iterations), "resampling_block_size": 2,
            "resampling_gap_policy": "STOP_AT_CALENDAR_AND_CONDITIONAL_SAMPLE_GAPS",
            "knowledge_bound": "MAX_AVAILABILITY_RELEASE_ACQUISITION_AND_VERIFICATION",
            "training_purge": "MAX_FEATURE_AND_TARGET_KNOWN_BEFORE_FIRST_TEST_FEATURE_KNOWN",
            "monthly_feature_proof": {
                "source_url": "monthly_revenue_source_url", "release_date": "monthly_source_release_date",
                "value_verification": "monthly_revenue_value_verification", "accepted_value_verification": sorted(_VALUE_MATCHES),
                "evidence_id": "monthly_revenue_evidence_id", "accounting_basis": "monthly_revenue_accounting_basis",
                "accepted_accounting_basis": _MONTHLY_ACCOUNTING_BASIS, "pit_exact": "monthly_revenue_pit_exact",
                "verification_bound": "monthly_revenue_verification_available_at",
                "acquisition_bounds": ["monthly_revenue_acquired_at", "monthly_revenue_snapshot_acquired_at"],
                "financial_metadata_verifies_monthly_feature": False,
            },
            "date_only_availability_timezone": "Asia/Taipei", "date_only_availability_bound": "END_OF_DAY",
            "scope": "COMPANY_TOTAL_PROXY", "forecast_beta_policy": "NULL_FOR_COMPANY_TOTAL_PROXY",
            "selection_policy": "PREDECLARED_NO_WINNER_SELECTION",
        },
        "coverage": {
            "input_rows": len(panel), "relevant_input_rows": relevant_count, "usable_input_rows": usable,
            "excluded_input_rows": relevant_count - usable, "exclusion_reasons": dict(sorted(excluded.items())),
            "companies": {company: len(rows) for company, rows in companies.items()},
            "comparisons": 72, "comparisons_with_samples": sum(r["sample_size"] > 0 for r in comparisons),
            "forecast_eligible_comparisons": 0,
        },
    }
