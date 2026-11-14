"""Coverage and quality evidence derived from existing analysis responses.

This module never retrieves or invents observations.  It normalizes the temporal
evidence already returned by each dataset so the UI can distinguish availability,
quality exclusion, provisional data, and time outside a product's record.
"""

from collections import Counter
from datetime import date, timedelta
import math
from typing import Any, Iterable

from app.comparison.catalog import DatasetEntry


STATUSES = ("valid", "missing", "excluded", "provisional", "outside_coverage", "unavailable")
MISSING_STATUSES = {"no_images", "no_valid_values", "missing"}
EXCLUDED_STATUSES = {"invalid_values", "insufficient_coverage", "excluded"}


def _month_starts(start: date, end: date) -> Iterable[date]:
    current = start.replace(day=1)
    while current < end:
        yield current
        current = (current + timedelta(days=32)).replace(day=1)


def _catalog_bounds(entry: DatasetEntry) -> tuple[date, date | None]:
    return date.fromisoformat(entry.available_from), date.fromisoformat(entry.available_to) if entry.available_to else None


def _period_supported(period_start: date, period_end: date, available_start: date, available_end: date | None) -> bool:
    # Catalog end dates are inclusive; period_end is exclusive.
    return period_end > available_start and (available_end is None or period_start <= available_end)


def _monthly_status(row: dict[str, Any] | None) -> tuple[str, list[str], float | None]:
    if row is None:
        return "missing", ["no_monthly_record"], None
    value = row.get("value")
    if "status" not in row:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return "valid", [], float(value)
        return "missing", ["no_valid_value"], None
    source_status = str(row.get("status") or "unavailable")
    reasons = list(row.get("reasons") or ([] if source_status == "valid" else [source_status]))
    if source_status == "valid" and row.get("usable", True) and value is not None:
        return "valid", reasons, float(value)
    if source_status == "valid" and not row.get("usable", True):
        return "provisional", reasons or ["provisional_recent_product"], float(value) if value is not None else None
    if row.get("provisional"):
        return "provisional", reasons or ["provisional_recent_product"], float(value) if value is not None else None
    if source_status in MISSING_STATUSES:
        return "missing", reasons, None
    if source_status in EXCLUDED_STATUSES:
        return "excluded", reasons, None
    return "unavailable", reasons, None


def _annual_status(row: dict[str, Any] | None) -> tuple[str, list[str], float | None]:
    if row is None:
        return "unavailable", ["dataset_result_unavailable"], None
    reasons = list(row.get("reasons") or [])
    value = row.get("value")
    if value is None:
        return "missing", reasons or ["no_annual_value"], None
    if row.get("eligible"):
        return "valid", reasons, float(value)
    return "excluded", reasons or ["not_eligible_for_comparison"], float(value)


def evaluate_dataset(
    entry: DatasetEntry,
    analysis: dict[str, Any] | None,
    requested_start: date,
    requested_end: date,
) -> dict[str, Any]:
    """Return coverage evidence with a denominator limited to supported periods."""
    available_start, available_end = _catalog_bounds(entry)
    series = (analysis or {}).get("series") or []
    monthly_rows: dict[date, dict[str, Any]] = {}
    for row in series:
        try:
            period = date.fromisoformat(str(row.get("date", ""))[:10])
        except (TypeError, ValueError):
            continue
        if period.day == 1:
            monthly_rows[period] = row
    resolution = "monthly" if monthly_rows else "annual"
    cells: list[dict[str, Any]] = []

    if resolution == "monthly":
        for period in _month_starts(requested_start, requested_end):
            next_period = (period + timedelta(days=32)).replace(day=1)
            if not _period_supported(period, next_period, available_start, available_end):
                status, reasons, value = "outside_coverage", ["outside_dataset_record"], None
            else:
                status, reasons, value = _monthly_status(monthly_rows.get(period))
            cells.append({"period": period.strftime("%Y-%m"), "status": status, "reasons": reasons, "value": value})
        unit = "months"
        resolution_note = "Monthly coverage from genuine monthly observation and quality-control records."
    else:
        annual_rows = {int(row["year"]): row for row in (analysis or {}).get("annual") or [] if "year" in row}
        for year in range(requested_start.year, requested_end.year + (1 if requested_end.month > 1 else 0)):
            period_start, period_end = date(year, 1, 1), date(year + 1, 1, 1)
            if period_start >= requested_end:
                continue
            if not _period_supported(period_start, period_end, available_start, available_end):
                status, reasons, value = "outside_coverage", ["outside_dataset_record"], None
            else:
                status, reasons, value = _annual_status(annual_rows.get(year))
            cells.append({"period": str(year), "status": status, "reasons": reasons, "value": value})
        unit = "years"
        resolution_note = "Annual coverage: monthly quality-control information is not available for this dataset response."

    counts = Counter(cell["status"] for cell in cells)
    complete_counts = {status: counts.get(status, 0) for status in STATUSES}
    denominator = len(cells) - complete_counts["outside_coverage"]
    valid = complete_counts["valid"]
    percentage = valid / denominator * 100 if denominator else None
    annual = (analysis or {}).get("annual") or []
    return {
        "dataset": entry.key,
        "resolution": resolution,
        "resolution_note": resolution_note,
        "requested_period": {"start": requested_start.isoformat(), "end_exclusive": requested_end.isoformat()},
        "supported_period": {"start": entry.available_from, "end": entry.available_to},
        "cells": cells,
        "counts": complete_counts,
        "completeness": {
            "valid": valid,
            "expected_within_supported_coverage": denominator,
            "percentage": percentage,
            "label": f"Valid {unit} / Expected {unit} within supported dataset coverage",
        },
        "eligible_years": [row["year"] for row in annual if row.get("eligible")],
        "excluded_years": [
            {"year": row["year"], "reasons": list(row.get("reasons") or [])}
            for row in annual if not row.get("eligible")
        ],
    }
