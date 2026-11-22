"""Import and compare independent time series on an explicit calendar."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone, tzinfo
import hashlib
from io import StringIO
from itertools import islice
import json
import math
from pathlib import Path
import re
from statistics import mean
from typing import Iterator, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from core.correlation_engine import METHODS, _safe_corr
from core.multi_asset.official_sources import AVAILABILITY_METHOD, parse_fx, parse_prices
from core.research_workspace import metric_label


Frequency = Literal["D", "M", "Q"]
Aggregation = Literal["last", "mean", "sum"]
Transform = Literal["level", "diff", "return", "yoy"]
_FREQUENCIES = {"D": 0, "M": 1, "Q": 2}
_LAGS = range(-6, 7)
_DATE_ONLY_METHODS = {
    "page_publication_date", "actual_release_date", "actual_publication_date",
    "exact_release_date", "release_date_only", "date_only",
}


def _csv_records(text: str) -> Iterator[list[str]]:
    reader = csv.reader(StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
    try:
        for row in reader:
            if row and (len(row) > 1 or row[0].strip()):
                yield row
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV on line {reader.line_num}: {exc}") from exc


def _csv_table(text: str) -> tuple[list[str], Iterator[list[str]]]:
    records = _csv_records(text)
    headers = [header.strip() for header in next(records, [])]
    if any(not header for header in headers) or len(set(headers)) != len(headers):
        raise ValueError("CSV headers must be nonempty and cannot contain duplicate names")

    def rows():
        for row in records:
            if len(row) > len(headers):
                raise ValueError("CSV row has more fields than the header")
            yield row + [""] * (len(headers) - len(row))

    return headers, rows()


def preview_csv(text: str) -> dict:
    """Return header labels and up to five data records as strings."""
    headers, rows = _csv_table(text)
    return {"headers": headers, "rows": list(islice(rows, 5))}


def _date_and_frequency(value: str) -> tuple[date, str]:
    text = value.strip()
    if match := re.fullmatch(r"([0-9]{4})-?[Qq]([1-4])", text):
        year, quarter = map(int, match.groups())
        month = 3 * quarter
        return date(year, month, monthrange(year, month)[1]), "Q"
    if match := re.fullmatch(r"([0-9]{4})[-/]([0-9]{1,2})", text):
        year, month = map(int, match.groups())
        return date(year, month, monthrange(year, month)[1]), "M"
    if re.fullmatch(r"[0-9]{4}/[0-9]{1,2}/[0-9]{1,2}", text):
        return date(*map(int, text.split("/"))), "D"
    try:
        return date.fromisoformat(text), "D"
    except ValueError:
        # Preserve the observation's own calendar date even when it has an offset.
        return datetime.fromisoformat(text).date(), "D"


@dataclass(frozen=True, slots=True)
class _Availability:
    earliest: datetime
    latest: datetime


def _availability(
    value: str | None, timing: str = "", *, day_zone: tzinfo | None = None, legacy_import: bool = False,
) -> _Availability | None:
    if not value:
        return None
    text = value.strip()
    try:
        try:
            day = date.fromisoformat(text)
        except ValueError:
            timestamp = datetime.fromisoformat(text)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            # Older imports converted date-only releases to indistinguishable UTC midnights.
            ambiguous_midnight = legacy_import and text.endswith("T00:00:00+00:00")
            if timing.casefold() not in _DATE_ONLY_METHODS and not ambiguous_midnight:
                exact = timestamp.astimezone(timezone.utc)
                return _Availability(exact, exact)
            day_zone = day_zone or timestamp.tzinfo
            day = timestamp.astimezone(day_zone).date()
        zone = day_zone or timezone.utc
        return _Availability(
            datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc),
            datetime.combine(day, time.max, tzinfo=zone).astimezone(timezone.utc),
        )
    except (ValueError, OverflowError):
        return None


def _availability_fields(available: _Availability | None, prefix: str = "") -> dict:
    if available is None:
        return {f"{prefix}available": None}
    fields = {f"{prefix}available": available.latest.isoformat()}
    if available.earliest != available.latest:
        fields[f"{prefix}available_from"] = available.earliest.isoformat()
        fields[f"{prefix}available_until"] = available.latest.isoformat()
    return fields


def _point_availability(point: dict, timing: str, legacy_import: bool) -> _Availability | None:
    if "available_from" in point or "available_until" in point:
        start = _availability(point.get("available_from"))
        end = _availability(point.get("available_until"))
        if start is None or end is None or start.earliest > end.latest:
            return None
        return _Availability(start.earliest, end.latest)
    return _availability(point.get("available"), timing, legacy_import=legacy_import)


def _number(value: str | float | None) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _frequency(observations: dict[date, str], coarsest_label: str) -> str:
    if coarsest_label != "D":
        return coarsest_label
    if len(observations) < 2:
        return "D"
    dates = sorted(observations)
    months = [day.year * 12 + day.month for day in dates]
    gaps = [later - earlier for earlier, later in zip(months, months[1:])]
    same_day = len({day.day for day in dates}) == 1
    month_ends = all(day.day == monthrange(day.year, day.month)[1] for day in dates)
    if not (same_day or month_ends) or 0 in gaps:
        return "D"
    if min(gaps) == 3 and all(gap % 3 == 0 for gap in gaps):
        return "Q"
    if min(gaps) == 1:
        return "M"
    return "D"


def import_csv(
    text: str,
    filename: str,
    date_column: str,
    columns: list[str],
    available_column: str | None = None,
    source: str = "",
    unit: str = "",
    *,
    frequency: str | None = None,
) -> list[dict]:
    """Import one series per selected column, in selection order.

    Invalid dates and nonfinite values are counted in each series' import_summary.
    A column with no valid observations or duplicate finite values on one date
    fails the whole import. Naive availability timestamps are interpreted as UTC.
    Cadence is inferred per column. An override cannot be finer than any of
    the retained date labels.
    """
    if frequency is not None and frequency not in _FREQUENCIES:
        raise ValueError(f"Unsupported import frequency: {frequency}")
    headers, rows = _csv_table(text)
    columns = list(dict.fromkeys(columns))
    selected = [date_column, *columns]
    if available_column is not None:
        selected.append(available_column)
    missing = [column for column in selected if column not in headers]
    if missing:
        raise ValueError(f"Unknown CSV column(s): {', '.join(missing)}")

    positions = {header: idx for idx, header in enumerate(headers)}
    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    dates: dict[str, dict[date, str]] = {column: {} for column in columns}
    points: dict[str, dict[date, dict]] = {column: {} for column in columns}
    rows_read = invalid_dates = 0
    for rows_read, row in enumerate(rows, start=1):
        try:
            day, granularity = _date_and_frequency(row[positions[date_column]])
        except ValueError:
            invalid_dates += 1
            continue
        available = _availability(row[positions[available_column]]) if available_column is not None else None
        for column in columns:
            value = _number(row[positions[column]])
            if value is not None:
                if day in points[column]:
                    raise ValueError(f"Duplicate dated numeric value for {column!r} on {day.isoformat()}")
                dates[column][day] = granularity
                points[column][day] = {
                    "date": day.isoformat(),
                    "value": value,
                    **_availability_fields(available),
                }
    empty = [column for column, observations in points.items() if not observations]
    if empty:
        raise ValueError(f"No valid dated numeric values in CSV column(s): {', '.join(empty)}")

    result = []
    for column, observations in points.items():
        coarsest_label = max(dates[column].values(), key=_FREQUENCIES.__getitem__)
        if frequency is not None and _FREQUENCIES[frequency] < _FREQUENCIES[coarsest_label]:
            raise ValueError(f"Import frequency {frequency} is finer than a date label in column {column!r}")
        cadence = frequency or _frequency(dates[column], coarsest_label)
        identity_fields = [filename, file_hash, date_column, column, available_column, source, unit]
        if frequency is not None:
            identity_fields.append(frequency)
        identity = json.dumps(identity_fields)
        result.append({
            "id": f"csv:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}",
            "name": column,
            "category": "Imported",
            "source": source or filename,
            "unit": unit,
            "frequency": cadence,
            "points": [observations[day] for day in sorted(observations)],
            "provenance": {"filename": filename, "column": column, "content_hash": file_hash},
            "import_summary": {
                "rows_read": rows_read,
                "skipped_invalid_dates": invalid_dates,
                "skipped_missing_or_nonnumeric_values": rows_read - invalid_dates - len(observations),
                "missing_availability": sum(point["available"] is None for point in observations.values()),
            },
        })
    return result


def _builtin_point(
    day: str, value: float, timestamp: str | None, timing: str, *, day_zone: tzinfo | None = None,
) -> dict:
    return {
        "date": day,
        "value": value,
        **_availability_fields(_availability(timestamp, timing, day_zone=day_zone)),
        "timing": timing,
    }


def _monthly_catalog(path: Path) -> list[dict]:
    catalog: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            day, frequency = _date_and_frequency(row["period"])
            value = _number(row["change_pct"])
            if frequency != "M" or value is None:
                continue
            identifier = row["metric_id"]
            series = catalog.setdefault(identifier, {
                "id": identifier, "name": metric_label(identifier),
                "category": "Company Revenue" if "::" in identifier else "Industry / Macro",
                "source": row["source"], "source_url": row["source_url"],
                "unit": "%", "frequency": "M", "points": [],
            })
            day_zone = ZoneInfo("Asia/Taipei") if row.get("source_id") == "tpca_public_industry" else None
            point = _builtin_point(
                day.isoformat(), value, row["published_at"], row["knowledge_time_method"], day_zone=day_zone,
            )
            point["source_url"] = row["source_url"]
            series["points"].append(point)
    return list(catalog.values())


def _quarterly_catalog(path: Path) -> list[dict]:
    # These records are consolidated standalone quarters, with actual audit
    # acquisition times. The other tracked quarterly file has cumulative flows.
    records = json.loads(path.read_text(encoding="utf-8"))["quarter_records"]
    catalog: dict[str, dict] = {}
    for row in records:
        if (row["accounting_basis"], row["evidence_status"], row["source_scope"], row["consolidation"]) != (
            "STANDALONE_QUARTER", "DISCLOSED", "COMPANY_TOTAL", "CONSOLIDATED",
        ):
            continue
        for field, label in (("revenue", "Revenue"), ("gross_profit", "Gross profit")):
            value = _number(row[field])
            if value is None:
                continue
            company = row["company"]
            identifier = f"quarterly_{field}::{company}"
            series = catalog.setdefault(identifier, {
                "id": identifier, "name": f"{company} • Quarterly {label.lower()}",
                "category": "Company Financials", "source": "TWSE/MOPS disclosures (audited historical evidence)",
                "unit": row["unit"], "frequency": "Q", "points": [],
            })
            point = _builtin_point(row["period_end"], value, row["available_at"], "audit_acquisition")
            point["source_url"] = row["source_url"]
            series["points"].append(point)
    return list(catalog.values())


def _market_catalog(fixtures: Path) -> list[dict]:
    provenance = fixtures / "provenance.json"
    if not provenance.is_file():
        return []
    sources = json.loads(provenance.read_text(encoding="utf-8"))["sources"]
    catalog = []
    for source in sources:
        if source["name"] not in {"cbc-fx", "price-0050"}:
            continue
        path = fixtures / source["path"]
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if source["name"] == "cbc-fx":
            rows = parse_fx(raw, source)
            identifier, name, unit = "cbc_usd_twd", "USD/TWD interbank close", "TWD per USD"
            category, provider, field = "Currency", "CBC", "rate"
        else:
            rows = parse_prices(raw, source, "0050", source["month"])
            identifier, name, unit = "twse_0050_close", "0050 unadjusted close", "TWD per unit"
            category, provider, field = "Market", "TWSE", "value"
        catalog.append({
            "id": identifier, "name": f"{name} (historical)", "category": category,
            "source": f"{provider} official historical snapshot", "source_url": source["source_url"],
            "unit": unit, "frequency": "D",
            "points": [
                _builtin_point(row["period"], row[field], row["acquired_at"], AVAILABILITY_METHOD)
                for row in rows if row[field] is not None
            ],
        })
    return [series for series in catalog if series["points"]]


def builtin_catalog(root: Path) -> list[dict]:
    """Load shipped historical industry, quarterly financial and market series."""
    catalog = _market_catalog(root / "tests" / "fixtures" / "taiwan_official")
    monthly = root / "data" / "research_workspace_snapshot.csv"
    if monthly.is_file():
        catalog.extend(_monthly_catalog(monthly))
    quarterly = root / "data" / "abf_quarterly_financial_evidence.json"
    if quarterly.is_file():
        catalog.extend(_quarterly_catalog(quarterly))
    for series in catalog:
        series["points"].sort(key=lambda point: point["date"])
    return catalog


@dataclass(frozen=True, slots=True)
class _Observation:
    value: float
    available: _Availability | None
    timing: str = ""
    source_urls: tuple[str, ...] = ()


def _period(day: date, frequency: Frequency) -> int:
    if frequency == "D":
        return day.toordinal()
    month = day.year * 12 + day.month - 1
    return month if frequency == "M" else month // 3


def _period_end(period: int, frequency: Frequency) -> date:
    if frequency == "D":
        return date.fromordinal(period)
    year, month_index = divmod(period if frequency == "M" else period * 3 + 2, 12)
    month = month_index + 1
    return date(year, month, monthrange(year, month)[1])


def _bounds(
    frequency: Frequency, aggregation: Aggregation, start: str | None, end: str | None,
) -> tuple[int, int]:
    if frequency not in _FREQUENCIES:
        raise ValueError(f"Unsupported frequency: {frequency}")
    if aggregation not in ("last", "mean", "sum"):
        raise ValueError(f"Unsupported aggregation: {aggregation}")
    first = _period(_date_and_frequency(start)[0] if start is not None else date.min, frequency)
    last = _period(_date_and_frequency(end)[0] if end is not None else date.max, frequency)
    if first > last:
        raise ValueError("Start period is after end period")
    return first, last


def _frequency_step(series: dict, frequency: Frequency) -> int:
    return _FREQUENCIES[frequency] - _FREQUENCIES.get(series.get("frequency"), 0)


def _derived(value: float, inputs: list[_Observation]) -> _Observation:
    times = [point.available for point in inputs if point.available is not None]
    availability = None
    if len(times) == len(inputs):
        availability = _Availability(max(interval.earliest for interval in times),
                                     max(interval.latest for interval in times))
    methods = {point.timing for point in inputs if point.timing}
    urls = dict.fromkeys(url for point in inputs for url in point.source_urls)
    return _Observation(
        value, availability, " | ".join(sorted(methods)), tuple(urls),
    )


def _resample(
    series: dict, frequency: Frequency, aggregation: Aggregation,
) -> dict[int, _Observation | None]:
    step = _frequency_step(series, frequency)
    if step < 0:
        return {}
    bins: dict[int, list[tuple[date, _Observation]]] = defaultdict(list)
    series_timing = series.get("timing") or series.get("knowledge_time_method") or ""
    legacy_import = series.get("category") == "Imported" and "provenance" not in series
    for point in series["points"]:
        value = _number(point["value"])
        if value is None:
            continue
        day = date.fromisoformat(point["date"])
        timing = point.get("timing") or point.get("knowledge_time_method") or series_timing
        url = point.get("source_url") or series.get("source_url")
        available = _point_availability(point, timing, legacy_import)
        observation = _Observation(value, available, timing, (url,) if url else ())
        bins[_period(day, frequency)].append((day, observation))

    result: dict[int, _Observation | None] = {}
    for period, dated_points in bins.items():
        if aggregation == "last":
            observation = max(dated_points, key=lambda item: item[0])[1]
        else:
            observations = [point for _, point in sorted(dated_points, key=lambda item: item[0])]
            values = [point.value for point in observations]
            try:
                value = mean(values) if aggregation == "mean" else math.fsum(values)
            except OverflowError:
                value = math.inf
            observation = _derived(value, observations) if math.isfinite(value) else None
        if step > 0 and observation is not None and observation.available is not None:
            close = datetime.combine(_period_end(period, frequency), time.max, tzinfo=timezone.utc)
            if observation.available.earliest < close:
                observation = replace(observation, available=_Availability(close, max(close, observation.available.latest)))
        result[period] = observation
    return result


def _prior_year(period: int, frequency: Frequency) -> int | None:
    if frequency != "D":
        return period - (12 if frequency == "M" else 4)
    day = date.fromordinal(period)
    try:
        return day.replace(year=day.year - 1).toordinal()
    except ValueError:  # February 29 without an anniversary, or a date in year 1.
        return None


def _transform(
    bins: dict[int, _Observation | None], frequency: Frequency, transform: Transform,
) -> dict[int, _Observation]:
    if transform not in ("level", "diff", "return", "yoy"):
        raise ValueError(f"Unsupported transform: {transform}")
    observed = {period: point for period, point in bins.items() if point is not None}
    if transform == "level":
        return observed

    result = {}
    for period, current in observed.items():
        reference = _prior_year(period, frequency) if transform == "yoy" else period - 1
        previous = observed.get(reference) if reference is not None else None
        if previous is None:
            continue
        if transform == "diff":
            value = current.value - previous.value
        elif previous.value != 0:
            value = current.value / previous.value - 1
        else:
            continue
        if math.isfinite(value):
            result[period] = _derived(value, [previous, current])
    return result


def chart_data(
    series: dict, *, frequency: Frequency, aggregation: Aggregation, transform: Transform,
    start: str | None, end: str | None,
) -> list[dict]:
    """Return calendar-bin ends and transformed values for the inclusive range.

    Input history supports transforms at the first requested bin. One null at
    the start of each missing run breaks chart lines, with output proportional
    to observed data even across very long daily spans.
    """
    first, last = _bounds(frequency, aggregation, start, end)
    bins = _resample(series, frequency, aggregation)
    values = _transform(bins, frequency, transform)
    if not bins:
        return []
    first, last = max(first, min(bins)), min(last, max(bins))
    result = []
    next_period = first
    for period in sorted(p for p in values if first <= p <= last):
        if next_period < period:
            result.append({"date": _period_end(next_period, frequency).isoformat(), "value": None})
        result.append({"date": _period_end(period, frequency).isoformat(), "value": values[period].value})
        next_period = period + 1
    if next_period <= last:
        result.append({"date": _period_end(next_period, frequency).isoformat(), "value": None})
    return result


def _timing_issues(x: _Observation, y: _Observation) -> set[str]:
    issues = set()
    if x.available is None or y.available is None:
        issues.add("missing")
    elif x.available.earliest > y.available.latest:
        issues.add("late")
    elif x.available.latest > y.available.earliest:
        issues.add("uncertain_order")
    timing = f"{x.timing} | {y.timing}".casefold()
    if any(marker in timing for marker in ("proxy", "acquisition", "estimate", "inferred", "unknown")):
        issues.add("unrecorded")
    return issues


def _align(
    x: dict[int, _Observation], y: list[tuple[int, _Observation]], lag: int,
    strict: bool, all_issues: set[str],
) -> list[tuple[int, _Observation, _Observation]]:
    aligned = []
    for target_period, target in y:
        feature = x.get(target_period - lag)
        if feature is None:
            continue
        issues = _timing_issues(feature, target)
        all_issues.update(issues)
        if not strict or not issues:
            aligned.append((target_period, feature, target))
    return aligned


def _pair_frame(aligned: list[tuple[int, _Observation, _Observation]]) -> pd.DataFrame:
    return pd.DataFrame([(x.value, y.value) for _, x, y in aligned], columns=["x", "y"], dtype=float)


def _center_for_pearson(values: np.ndarray) -> np.ndarray | None:
    low, high = float(values.min()), float(values.max())
    if low == high:
        return None
    # Subtract a nearby endpoint before scaling to retain small differences.
    # Use zero across signs so subtraction cannot exceed the float range.
    origin = low if low >= 0 else min(high, 0.0)
    scale = max(high - origin, origin - low)
    scaled = (values - origin) / scale
    return scaled - scaled.mean()


def _pearson(pair: pd.DataFrame) -> float | None:
    if len(pair) < 2:
        return None
    x = _center_for_pearson(pair["x"].to_numpy())
    y = _center_for_pearson(pair["y"].to_numpy())
    if x is None or y is None:
        return None
    scale = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y)))
    correlation = float(np.dot(x, y)) / scale
    return min(1.0, max(-1.0, correlation))


def _coefficients(pair: pd.DataFrame) -> dict[str, float | None]:
    spearman = _safe_corr(pair, "spearman")
    return {"pearson": _pearson(pair), "spearman": spearman if math.isfinite(spearman) else None}


def _sample_provenance(x: dict, y: dict) -> dict:
    fields = {}
    for side, series in (("x", x), ("y", y)):
        fields[f"{side}_source"] = series.get("source")
        provenance = series.get("provenance") or {}
        for key in ("filename", "column", "content_hash"):
            fields[f"{side}_{key}"] = provenance.get(key)
    return fields


def _sample(period: int, lag: int, frequency: Frequency, x: _Observation, y: _Observation) -> dict:
    row = {
        "x_date": _period_end(period - lag, frequency).isoformat(),
        "y_date": _period_end(period, frequency).isoformat(),
        "x": x.value,
        "y": y.value,
        **_availability_fields(x.available, "x_"),
        **_availability_fields(y.available, "y_"),
    }
    for side, observation in (("x", x), ("y", y)):
        if observation.timing:
            row[f"{side}_timing"] = observation.timing
        if observation.source_urls:
            row[f"{side}_source_url"] = " | ".join(observation.source_urls)
    return row


def analyze(
    x: dict, y: dict, *, frequency: Frequency, aggregation: Aggregation,
    x_transform: Transform, y_transform: Transform, start: str | None, end: str | None,
    lag: int, window: int, strict: bool,
) -> dict:
    """Compare X(t) with Y(t + lag), using the exact calendar bins.

    Start and end select whole target (Y) bins inclusively. All available
    input history is consulted for lagged X and for transforms. Differences
    and fractional returns use the immediately prior bin. YoY returns use the
    same date in the prior year for D or the prior year's bin for M/Q.
    Known downsampled availability is floored at bin close (end of day UTC).
    Strict mode requires the latest recorded X availability to be no later
    than the earliest recorded Y availability. Date-only releases use a full
    day. Samples report the latest bound and include both bounds for intervals.
    Sample source URLs follow their contributing values in chronological order.
    Rolling coefficients use the last `window` retained pairs. The scan always
    covers lags -6 through +6, and the selected lag can be outside that scan.
    """
    if type(lag) is not int or type(window) is not int or window < 1:
        raise ValueError("Lag must be an integer and window must be a positive integer")
    first, last = _bounds(frequency, aggregation, start, end)
    x_values = _transform(_resample(x, frequency, aggregation), frequency, x_transform)
    y_values = _transform(_resample(y, frequency, aggregation), frequency, y_transform)
    targets = sorted((period, point) for period, point in y_values.items() if first <= period <= last)

    selected_issues: set[str] = set()
    scan_issues: set[str] = set()
    aligned = _align(x_values, targets, lag, strict, selected_issues)
    pair = _pair_frame(aligned)
    coefficients = _coefficients(pair)
    scan = []
    for offset in _LAGS:
        if offset == lag:
            scan.append({"lag": offset, "n": len(pair), **coefficients})
        else:
            candidate = _pair_frame(_align(x_values, targets, offset, strict, scan_issues))
            scan.append({"lag": offset, "n": len(candidate), **_coefficients(candidate)})

    provenance = _sample_provenance(x, y)
    samples = [_sample(period, lag, frequency, x_point, y_point) | provenance
               for period, x_point, y_point in aligned]
    rolling = []
    for end_index, row in enumerate(samples, start=1):
        stats = (
            _coefficients(pair.iloc[end_index - window:end_index])
            if end_index >= window else dict.fromkeys(METHODS)
        )
        rolling.append({"date": row["y_date"], **stats})

    warnings = []
    frequency_steps = {"X": _frequency_step(x, frequency), "Y": _frequency_step(y, frequency)}
    for side, step in frequency_steps.items():
        if step < 0:
            warnings.append(f"{side} has a coarser native frequency. Upsampling is disabled.")
    if any(step > 0 for step in frequency_steps.values()):
        warnings.append("Downsampled observations with known timestamps use their UTC bin close as earliest availability.")
    issues_text = {
        "missing": "pairs with missing availability timestamps",
        "unrecorded": "pairs with proxy, acquisition-only or other unverified timing",
        "late": "pairs where the X timestamp is after the Y timestamp",
        "uncertain_order": "pairs whose overlapping release windows leave the X and Y order uncertain",
    }
    for issue, message in issues_text.items():
        action = "excluded" if strict else "includes"
        if issue in selected_issues:
            warnings.append(f"Selected lag {action} {message}.")
        elif issue in scan_issues:
            warnings.append(f"Lag scan {action} {message}.")
    if not samples:
        warnings.append("No aligned samples at the selected lag.")
    return {
        **coefficients, "n": len(samples), "rolling": rolling, "lags": scan,
        "samples": samples, "warnings": warnings,
    }
