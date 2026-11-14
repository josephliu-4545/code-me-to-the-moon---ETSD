"""Generic Earth Engine monthly pipeline for alternative datasets.

One loader serves four sampling methods (sub-daily mean, monthly value, daily sum,
monthly sum). Values come from the exact native grid cell containing the point.
Validation, coverage rules, unit conversion and annual aggregation are pure Python
so they can be tested without Earth Engine. Missing months stay missing; samples
outside the physical range invalidate the month (never clipped).
"""

from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import calendar
import math
import time
from statistics import mean
from threading import Lock
from typing import Any, Callable

from app.comparison.catalog import DatasetEntry
from app.core.earth_engine import EarthEngineError
from app.services.soil_moisture_provider import UnsupportedLocationError
from app.statistics.models import AnnualSummary
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


class ComparisonRetrievalError(RuntimeError):
    """Malformed or inconsistent provider data (maps to HTTP 502)."""


@dataclass(frozen=True)
class Cell:
    cell_id: str
    center: tuple[float, float]
    south: float
    north: float
    west: float
    east: float
    size_degrees: float


@dataclass(frozen=True)
class MonthlyValue:
    month: date
    value: float | None          # canonical units; None unless status == "valid"
    expected_samples: int
    valid_samples: int
    images: int
    invalid_samples: int
    provisional: bool
    status: str                  # valid | insufficient_coverage | no_valid_values | no_images | invalid_values

    @property
    def usable(self) -> bool:
        return self.status == "valid" and not self.provisional


def native_cell(entry: DatasetEntry, lat: float, lon: float) -> Cell:
    dx, _, x0, _, ndy, y0 = entry.crs_transform  # type: ignore[misc]
    dy = -ndy
    cols = round(360 / dx)
    col = min(cols - 1, max(0, math.floor((lon - x0) / dx)))
    row = max(0, math.floor((y0 - lat) / dy))
    west, north = x0 + col * dx, y0 - row * dy
    r = lambda v: round(v, 6)
    return Cell(f"{entry.key}:{row}:{col}", (r(north - dy / 2), r(west + dx / 2)), r(north - dy), r(north), r(west), r(west + dx), dx)


def check_supported(entry: DatasetEntry, lat: float) -> None:
    lo, hi = entry.latitude_limits
    if not lo <= lat <= hi:
        raise UnsupportedLocationError("outside_dataset_coverage", f"{entry.name} covers latitudes {lo:g}° to {hi:g}° only")


def _months(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def expected_samples(entry: DatasetEntry, month: date) -> int:
    days = calendar.monthrange(month.year, month.month)[1]
    if entry.method == "subdaily_mean":
        n = days * entry.extra.get("expected_slots_per_day", 8)
        return n - entry.extra.get("record_start_missing_slots", {}).get(month.strftime("%Y-%m"), 0)
    if entry.method == "daily_sum":
        return days
    return 1


def _is_count(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 and float(v).is_integer()


def normalize_rows(entry: DatasetEntry, rows: object, start: date, end: date) -> list[MonthlyValue]:
    if not isinstance(rows, list):
        raise ComparisonRetrievalError("malformed provider response")
    by_month: dict[date, list] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 7 or not isinstance(row[0], str):
            raise ComparisonRetrievalError("malformed provider row")
        try:
            month = date.fromisoformat(row[0][:10])
        except ValueError as exc:
            raise ComparisonRetrievalError("invalid month") from exc
        if month in by_month or month.day != 1:
            raise ComparisonRetrievalError("duplicate or misaligned month")
        by_month[month] = list(row)
    out = []
    for month in _months(start, end):
        expected = expected_samples(entry, month)
        row = by_month.get(month)
        if row is None:
            out.append(MonthlyValue(month, None, expected, 0, 0, 0, False, "no_images"))
            continue
        _, images, raw, valid, agg, permanent, status_known = row
        counts = [images, raw or 0, valid or 0, permanent, status_known]
        if not all(_is_count(c) for c in counts):
            raise ComparisonRetrievalError("invalid provider counts")
        images, raw, valid, permanent, status_known = (int(c) for c in counts)
        if valid > raw or raw > images or valid > expected:
            raise ComparisonRetrievalError("inconsistent provider counts")
        provisional = bool(entry.status_property) and status_known == images and permanent < images
        invalid = raw - valid
        if images == 0:
            status, value = "no_images", None
        elif invalid > 0:
            status, value = "invalid_values", None
        elif valid == 0:
            status, value = "no_valid_values", None
        elif valid / expected < entry.min_month_coverage:
            status, value = "insufficient_coverage", None
        else:
            if not isinstance(agg, (int, float)) or isinstance(agg, bool) or not math.isfinite(agg):
                raise ComparisonRetrievalError("non-finite monthly aggregate")
            status, value = "valid", agg * entry.scale + entry.offset
        out.append(MonthlyValue(month, value, expected, valid, images, invalid, provisional, status))
    return out


def annual_summaries(entry: DatasetEntry, months: list[MonthlyValue]) -> list[AnnualSummary]:
    by_year: dict[int, list[MonthlyValue]] = defaultdict(list)
    for m in months:
        by_year[m.month.year].append(m)
    summaries = []
    for year in sorted(by_year):
        items = by_year[year]
        usable = [m for m in items if m.usable]
        represented = tuple(m.month.month for m in usable)
        missing = tuple(mo for mo in range(1, 13) if mo not in represented)
        quarters = tuple(sorted({(mo - 1) // 3 + 1 for mo in represented}))
        complete = len(items) == 12
        reasons = []
        if not complete:
            reasons.append("partial_calendar_year")
        if not usable:
            reasons.append("no_valid_observations")
        if len(usable) < 12:
            reasons.append("insufficient_represented_months")
        if any(m.provisional for m in items):
            reasons.append("provisional_recent_product")
        if any(m.status == "invalid_values" for m in items):
            reasons.append("invalid_monthly_values")
        values = [m.value for m in usable]
        if entry.annual_rule == "sum":
            annual = sum(values) if complete and len(usable) == 12 else None
        else:
            annual = mean(values) if values else None
        with_images = sum(1 for m in items if m.images > 0)
        summaries.append(AnnualSummary(
            year=year, annual_value=annual, value_units=entry.units,
            monthly_values=tuple((m.month.month, m.value) for m in usable),
            represented_months=represented, missing_months=missing,
            represented_quarters=quarters, missing_quarters=tuple(q for q in range(1, 5) if q not in quarters),
            valid_observations=len(usable), used_observations=len(usable), expected_observations=len(items),
            available_images=with_images, valid_coverage_percentage=len(usable) / len(items) * 100,
            image_availability_percentage=with_images / len(items) * 100,
            is_complete_calendar_year=complete, eligible_for_trend_inference=not reasons,
            eligibility_reasons=tuple(reasons), minimum_spatial_coverage_percentage=None,
            mean_spatial_coverage_percentage=None, median_spatial_coverage_percentage=None,
            spatial_coverage_threshold_applied=None,
        ))
    return summaries


def analyze_months(entry: DatasetEntry, months: list[MonthlyValue], trend_policy: TrendPolicy | None = None):
    summaries = tuple(annual_summaries(entry, months))
    trend = analyze_trend(summaries, entry.units if entry.annual_rule == "mean" else "mm/year", trend_policy or TrendPolicy())
    if entry.annual_rule == "sum" and trend.theil_sen is not None:
        from dataclasses import replace
        trend = replace(trend, theil_sen=replace(trend.theil_sen, slope_units=entry.slope_units))
    return summaries, trend


@dataclass(frozen=True)
class MonthlyResult:
    entry_key: str
    cell: Cell
    months: tuple[MonthlyValue, ...]


Loader = Callable[[DatasetEntry, Cell, date, date], object]


class EEMonthlyProvider:
    def __init__(self, manager: Any, window_years: int = 5, max_parallel: int = 5,
                 cache_max_entries: int = 64, cache_ttl_seconds: float = 3600,
                 loader: Loader | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._manager = manager
        self._window_years = window_years
        self._max_parallel = max(1, max_parallel)
        self._loader = loader or self._load_rows
        self._cache: OrderedDict[tuple, tuple[float, MonthlyResult]] = OrderedDict()
        self._cache_max, self._cache_ttl, self._clock = cache_max_entries, cache_ttl_seconds, clock
        self._lock = Lock()

    def fetch(self, entry: DatasetEntry, lat: float, lon: float, start: date, end: date) -> MonthlyResult:
        check_supported(entry, lat)
        cell = native_cell(entry, lat, lon)
        key = (entry.key, entry.version, cell.cell_id, start, end)
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] <= self._cache_ttl:
                return hit[1]
        self._manager.initialize()
        windows, s = [], start
        while s < end:
            e = min(date(s.year + self._window_years, s.month, 1), end)
            windows.append((s, e))
            s = e
        try:
            if len(windows) > 1 and self._max_parallel > 1:
                with ThreadPoolExecutor(max_workers=min(self._max_parallel, len(windows))) as pool:
                    parts = list(pool.map(lambda w: self._loader(entry, cell, w[0], w[1]), windows))
            else:
                parts = [self._loader(entry, cell, a, b) for a, b in windows]
        except (EarthEngineError, ComparisonRetrievalError, UnsupportedLocationError):
            raise
        except Exception as exc:
            raise ComparisonRetrievalError("Earth Engine retrieval failed") from exc
        rows: list = []
        for part in parts:
            if not isinstance(part, list):
                raise ComparisonRetrievalError("malformed provider response")
            rows.extend(part)
        result = MonthlyResult(entry.key, cell, tuple(normalize_rows(entry, rows, start, end)))
        if not any(m.provisional for m in result.months):
            with self._lock:
                self._cache[key] = (self._clock(), result)
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
        return result

    def _load_rows(self, entry: DatasetEntry, cell: Cell, start: date, end: date) -> object:
        ee = self._manager.ee
        point = ee.Geometry.Point([cell.center[1], cell.center[0]])
        transform = list(entry.crs_transform)  # type: ignore[arg-type]
        lo, hi = entry.valid_range or (-1e30, 1e30)
        nlo, nhi = sorted(((lo - entry.offset) / entry.scale, (hi - entry.offset) / entry.scale))
        coll = ee.ImageCollection(entry.collection_id).filterDate(start.isoformat(), end.isoformat()).select(entry.band)
        reducer_sum = entry.method == "daily_sum"
        status = entry.status_property

        def per_month(month_iso):
            m = ee.Date(month_iso)
            c = coll.filterDate(m, m.advance(1, "month"))
            in_range = c.map(lambda im: im.updateMask(im.gte(nlo).And(im.lte(nhi))))
            agg = in_range.sum() if reducer_sum else in_range.mean()
            stats = ee.Image.cat([c.count().rename("raw"), in_range.count().rename("valid"), agg.rename("agg")]).reduceRegion(
                ee.Reducer.first(), point, crs="EPSG:4326", crsTransform=transform)
            size = c.size()
            permanent = c.filter(ee.Filter.eq(status, "permanent")).size() if status else size
            known = c.filter(ee.Filter.notNull([status])).size() if status else size
            return ee.Algorithms.If(size.gt(0), ee.List([
                month_iso, size, stats.get("raw"), stats.get("valid"), stats.get("agg"), permanent, known,
            ]), ee.List([month_iso, 0, 0, 0, None, 0, 0]))

        return ee.List([m.isoformat() for m in _months(start, end)]).map(per_month).getInfo()


def normalise_monthly(entry: DatasetEntry, result: MonthlyResult, summaries, trend, lat: float, lon: float,
                      start: date, end: date, trend_payload: Callable[[dict], dict], caveats: list[str],
                      trend_method: dict) -> dict[str, Any]:
    """Build the /api/v2 analysis envelope for an alternative dataset."""
    cell = result.cell
    annual = [{
        "year": s.year, "value": s.annual_value, "eligible": s.eligible_for_trend_inference,
        "reasons": list(s.eligibility_reasons), "complete_calendar_year": s.is_complete_calendar_year,
        "coverage_percentage": s.valid_coverage_percentage, "represented_months": list(s.represented_months),
        "missing_months": list(s.missing_months),
        "extra": ({"observed_sum_of_valid_months": sum(v for _, v in s.monthly_values)} if entry.annual_rule == "sum" else {}),
    } for s in summaries]
    status_counts: dict[str, int] = defaultdict(int)
    for m in result.months:
        status_counts[m.status] += 1
    return {
        "variable": {"id": entry.variable, "name": entry.name, "description": entry.measurement,
                     "annual_value_definition": entry.measurement.split("; ")[-1]},
        "dataset": {"source": entry.provider, "id": entry.collection_id, "version": entry.version,
                    "provenance": entry.product_type, "doi": entry.doi, "key": entry.key, "title": entry.name,
                    "citation": entry.citation},
        "spatial_support": {
            "mode": "point", "type": "native_grid_cell",
            "description": f"Native {cell.size_degrees:g}° grid cell containing the point (no substitution)",
            "native_grid": f"{cell.size_degrees:g}°", "resolution": entry.spatial_resolution,
            "cell": {"id": cell.cell_id, "center": list(cell.center),
                     "bounds": {"south": cell.south, "north": cell.north, "west": cell.west, "east": cell.east},
                     "approximate": False},
            "cell_status": "ok" if any(m.status == "valid" for m in result.months) else "no_valid_values",
            "requested": {"latitude": lat, "longitude": lon},
        },
        "period": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "units": {"annual_value": entry.units, "slope": entry.slope_units},
        "annual": annual,
        "series": [{"date": m.month.isoformat(), "value": m.value, "status": m.status, "usable": m.usable,
                    "descriptive_value": m.value} for m in result.months],
        "series_definition": ("monthly total (mm/month)" if entry.annual_rule == "sum" else f"monthly mean ({entry.units})"),
        "trend": trend_payload(asdict(trend)),
        "coverage": {"years_requested": len(annual), "eligible_years": sum(1 for a in annual if a["eligible"]),
                     "excluded_years": [{"year": a["year"], "reasons": a["reasons"]} for a in annual if not a["eligible"]]},
        "methodology": {"source": {"quality_control": entry.quality_control, "processing": entry.processing,
                                   "month_status_counts": dict(status_counts)},
                        "trend_method": trend_method},
        "caveats": caveats,
        "limitations": list(entry.limitations),
        "extra": {"month_status_counts": dict(status_counts)},
        "data_status": "live_nasa_retrieval" if entry.provider.startswith("NASA") else "live_provider_retrieval",
    }
