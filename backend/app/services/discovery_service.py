"""Feature 03/04 presentation contracts derived from normalized scientific results.

No alternative trend estimator lives here. Period means use eligible annual
summaries of the same product/footprint, not raw mixed-frequency observations.
"""
from datetime import date, timedelta
import hashlib
import json
import math
import re
from statistics import fmean

VERSION = "discovery-1"


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def result_identity(a):
    evidence = {k: a.get(k) for k in ("variable", "dataset", "spatial_support", "period", "units", "annual", "series", "trend", "methodology", "coverage", "caveats", "limitations")}
    raw = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256((VERSION + raw).encode()).hexdigest()


def history(a):
    start = date.fromisoformat(a["period"]["start"])
    end = date.fromisoformat(a["period"]["end_exclusive"])
    by_year = {p["year"]: p for p in a["annual"]}
    annual = []
    for year in range(start.year, (end - timedelta(days=1)).year + 1):
        p = by_year.get(year)
        value = p.get("value") if p else None
        valid = finite(value)
        eligible = bool(valid and p.get("eligible"))
        reasons = p.get("reasons", []) if p else ["not_returned"]
        annual.append({"date": str(year), "value": value if valid else None, "eligible": eligible,
                       "status": "eligible" if eligible else "excluded" if valid else "missing",
                       "reasons": reasons, "coverage_percentage": p.get("coverage_percentage") if p else None})
    monthly = []
    definition = a.get("series_definition")
    # An empty extreme-heat series means this product does not supply monthly observations.
    if definition:
        source = {p["date"][:7]: p for p in a["series"]}
        month = start.replace(day=1)
        while month < end:
            key = month.strftime("%Y-%m")
            p = source.get(key)
            value = p.get("value") if p else None
            valid = bool(p and finite(value) and p.get("usable") is not False)
            monthly.append({"date": key, "value": value if valid else None, "eligible": valid,
                            "status": "valid" if valid else "withheld" if p else "missing",
                            "reasons": [p["status"]] if p and p.get("status") else ([] if valid else ["not_returned" if not p else "no_usable_value"])})
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    match = re.search(r"\(([^)]+)\)\s*$", definition or "")
    return {"annual": annual, "monthly": monthly, "annual_units": a["units"]["annual_value"],
            "monthly_units": match.group(1) if match else a["units"]["annual_value"],
            "monthly_available": bool(definition), "end_exclusive": end.isoformat(), "interpolated": False}


def findings(a):
    t = a.get("trend") or {}
    slope = t.get("slope")
    seasonal = t.get("method") == "seasonal_kendall"
    mk = t.get("mann_kendall")
    supported = t.get("result_level") == "statistical_inference" and bool(mk)
    unavailable = (not finite(slope) or t.get("result_level") == "annual_summaries_only"
                   or a["spatial_support"].get("cell_status") == "no_valid_land_values")
    if unavailable:
        kind, label, inference = "unavailable", "Trend unavailable", "Trend unavailable"
        note = t.get("slope_unavailable_reason") or "Insufficient usable observations to estimate a trend; this does not establish absence of change."
        headline = "There is not enough supported data to determine a long-term trend."
    elif supported and mk["is_statistically_significant"] and slope != 0:
        up = slope > 0
        kind, label, inference = ("increasing", "Indicative increase", "Significant*") if up else ("decreasing", "Indicative decrease", "Significant*")
        note = "The reported test rejects no monotonic trend under its stated assumptions. Treat significance as indicative; see dependence and method limitations."
        headline = f"An {'upward' if up else 'downward'} signal in {a['variable']['name']}, indicated by the trend test."
    elif supported:
        kind, label, inference = "not_detected", "No trend detected", "Not significant"
        note = "The test did not detect a monotonic trend. This is not proof of no environmental change."
        headline = "The estimated slope is inconclusive under the reported trend test."
    else:
        kind, label, inference = "descriptive", "Descriptive slope only", "Descriptive"
        note = t.get("significance_unavailable_reason") or "A slope is available without a supported significance test."
        headline = "A descriptive rate of change, without a significance conclusion."
    years = t.get("eligible_years", [])
    units = t.get("slope_units") or a["units"]["slope"]
    decade_units = units.replace("/year²", "/year per decade") if units.endswith("/year²") else re.sub(r"/year$", "/decade", units)
    return {"kind": kind, "label": label, "inference": inference, "note": note, "headline": headline,
            "slope": None if unavailable else slope, "slope_units": units,
            "per_decade": None if unavailable else slope * 10, "per_decade_units": decade_units,
            "fitted_change": slope * (max(years) - min(years))
            if not unavailable and not seasonal and len(years) >= 2 else None,
            "slope_method": "Seasonal Sen slope" if seasonal else "Theil-Sen slope",
            "test_method": "Seasonal Kendall" if seasonal else "Mann-Kendall",
            "tested_null": "No monotonic trend", "test_reported": supported and not unavailable,
            "test": mk if supported and not unavailable else None,
            "confidence_interval": t.get("confidence_interval") if supported and not unavailable else None,
            "eligible_years": years, "serial_dependence": t.get("serial_dependence"),
            "limitations": list(dict.fromkeys(["A trend is not a forecast and does not identify a cause.",
                "Non-significance is not proof of no change. A slope interval is not a prediction interval.",
                *a.get("caveats", []), *a.get("limitations", [])]))}


def discovery(a):
    return {"analysis_id": result_identity(a), "contract_version": VERSION,
            "history": history(a), "findings": findings(a)}


def validate_windows(start, end, first_start, first_end, second_start, second_end):
    if first_start > first_end or second_start > second_end:
        raise ValueError("Each period's start year must be at or before its end year.")
    last = (end - timedelta(days=1)).year
    if min(first_start, second_start) < start.year or max(first_end, second_end) > last:
        raise ValueError("Both periods must be inside the submitted investigation.")
    if max(first_start, second_start) <= min(first_end, second_end):
        raise ValueError("Choose two non-overlapping periods.")


def compare_periods(a, first_start, first_end, second_start, second_end):
    validate_windows(date.fromisoformat(a["period"]["start"]), date.fromisoformat(a["period"]["end_exclusive"]),
                     first_start, first_end, second_start, second_end)
    def period(lo, hi):
        rows = {p["year"]: p for p in a["annual"]}
        eligible = [p for y, p in sorted(rows.items()) if lo <= y <= hi and p.get("eligible") and finite(p.get("value")) and p.get("complete_calendar_year") is not False]
        used = {p["year"] for p in eligible}
        return {"start_year": lo, "end_year_inclusive": hi, "expected_years": hi - lo + 1,
                "eligible_years": sorted(used), "count": len(eligible),
                "excluded_years": [{"year": y, "reasons": rows.get(y, {}).get("reasons") or ["not_eligible_or_missing"]} for y in range(lo, hi + 1) if y not in used],
                "mean": fmean(p["value"] for p in eligible) if eligible else None}
    first, second = period(first_start, first_end), period(second_start, second_end)
    available = first["mean"] is not None and second["mean"] is not None
    return {"analysis_id": result_identity(a), "first": first, "second": second,
            "status": "available" if available else "unavailable",
            "difference": second["mean"] - first["mean"] if available else None,
            "units": "percentage points" if a["variable"]["id"] in ("relative_humidity", "extreme_heat") else a["units"]["annual_value"],
            "annual_units": a["units"]["annual_value"],
            "statistic": "Equal-weighted mean of eligible annual summaries; second period minus first period.",
            "annual_value_definition": a["variable"]["annual_value_definition"],
            "warnings": ["Descriptive comparison, not a trend estimate, significance test, prediction or causal attribution.",
                         "Only eligible complete annual summaries are included. Unequal coverage can affect the comparison.",
                         "Annual precipitation totals are averaged across years, never summed across periods."]}
