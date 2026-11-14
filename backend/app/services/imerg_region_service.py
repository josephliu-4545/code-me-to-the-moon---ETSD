"""Region-wide (bounding box) IMERG V07 monthly precipitation.

Each month's regional value is an area-weighted mean precipitation rate over the
valid (unmasked) 0.1-degree pixels inside the box, using Earth Engine pixel areas;
partial edge pixels are weighted by their overlap. Months whose valid area is below
a configurable fraction of the box are treated as missing, never zero and never
filled. No single grid cell is substituted for the region.
"""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
import math
import time
from threading import Lock
from typing import Any, Callable

from app.core.earth_engine import EarthEngineError
from app.precipitation.aggregation import monthly_rate_to_accumulation
from app.precipitation.models import MonthlyPrecipitation, MonthlyPrecipitationSeries, PrecipitationQuery
from app.services.imerg_service import BAND, DATASET_ID, ImergRetrievalError


IMERG_TRANSFORM = [0.1, 0, -180.0, 0, -0.1, 90.0]


@dataclass(frozen=True)
class RegionBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        for name in ("west", "south", "east", "north"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if not -180 <= self.west < self.east <= 180:
            raise ValueError("west must be less than east, both within -180..180 (boxes crossing the antimeridian are not supported)")
        if not -90 <= self.south < self.north <= 90:
            raise ValueError("south must be less than north, both within -90..90")

    @property
    def width(self) -> float:
        return self.east - self.west

    @property
    def height(self) -> float:
        return self.north - self.south

    @property
    def center(self) -> tuple[float, float]:
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    def key(self) -> tuple[float, float, float, float]:
        return (round(self.west, 4), round(self.south, 4), round(self.east, 4), round(self.north, 4))


@dataclass(frozen=True)
class RegionMonthCoverage:
    month: date
    valid_area_km2: float
    total_area_km2: float
    valid_area_fraction: float
    accepted: bool


@dataclass(frozen=True)
class RegionPrecipitationSeries:
    series: MonthlyPrecipitationSeries
    box: RegionBox
    coverage: tuple[RegionMonthCoverage, ...]
    min_valid_area_fraction: float


RowLoader = Callable[[RegionBox, date, date], object]


class ImergRegionService:
    def __init__(
        self,
        manager: Any,
        window_years: int = 5,
        min_valid_area_fraction: float = 0.95,
        cache_max_entries: int = 32,
        cache_ttl_seconds: float = 3600,
        row_loader: RowLoader | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < min_valid_area_fraction <= 1:
            raise ValueError("minimum valid area fraction must be in (0, 1]")
        self._manager = manager
        self._window_years = window_years
        self.min_valid_area_fraction = min_valid_area_fraction
        self._row_loader = row_loader or self._load_rows_from_ee
        self._cache: OrderedDict[tuple, tuple[float, RegionPrecipitationSeries]] = OrderedDict()
        self._cache_max = cache_max_entries
        self._cache_ttl = cache_ttl_seconds
        self._clock = clock
        self._lock = Lock()

    def fetch_region(self, box: RegionBox, start: date, end: date) -> RegionPrecipitationSeries:
        key = (DATASET_ID, "07", box.key(), start, end, self.min_valid_area_fraction)
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] <= self._cache_ttl:
                self._cache.move_to_end(key)
                return hit[1]
        self._manager.initialize()
        rows: list[object] = []
        s = start
        try:
            while s < end:
                try:
                    candidate = s.replace(year=s.year + self._window_years)
                except ValueError:
                    candidate = s.replace(year=s.year + self._window_years, day=28)
                e = min(candidate, end)
                loaded = self._row_loader(box, s, e)
                if not isinstance(loaded, list):
                    raise ImergRetrievalError("malformed IMERG region response")
                rows.extend(loaded)
                s = e
            result = self._normalize(rows, box)
        except (EarthEngineError, ImergRetrievalError):
            raise
        except Exception as exc:
            raise ImergRetrievalError("Earth Engine IMERG region retrieval failed") from exc
        with self._lock:
            self._cache[key] = (self._clock(), result)
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
        return result

    def _normalize(self, rows: list[object], box: RegionBox) -> RegionPrecipitationSeries:
        observations, coverage, seen = [], [], set()
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 4 or not isinstance(row[0], str):
                raise ImergRetrievalError("malformed IMERG region row")
            try:
                month = date.fromisoformat(row[0][:10]).replace(day=1)
            except ValueError as exc:
                raise ImergRetrievalError("invalid IMERG month") from exc
            if month in seen:
                raise ImergRetrievalError("duplicate IMERG month")
            seen.add(month)
            weighted, valid_area, total_area = (0.0 if v is None else v for v in row[1:])
            for v in (weighted, valid_area, total_area):
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
                    raise ImergRetrievalError("invalid IMERG region sums")
            if total_area <= 0 or valid_area > total_area * (1 + 1e-9):
                raise ImergRetrievalError("inconsistent IMERG region areas")
            fraction = valid_area / total_area
            accepted = fraction >= self.min_valid_area_fraction and valid_area > 0
            rate = accumulation = None
            if accepted:
                rate = weighted / valid_area
                if rate < 0:
                    raise ImergRetrievalError("negative IMERG regional rate")
                accumulation = monthly_rate_to_accumulation(rate, month.year, month.month)
            observations.append(MonthlyPrecipitation(month, rate, accumulation, True))
            coverage.append(RegionMonthCoverage(month, valid_area / 1e6, total_area / 1e6, fraction, accepted))
        observations.sort(key=lambda o: o.month)
        coverage.sort(key=lambda c: c.month)
        series = MonthlyPrecipitationSeries(
            tuple(observations),
            f"imerg-v07-region:{box.west:.4f},{box.south:.4f},{box.east:.4f},{box.north:.4f}",
            box.center,
        )
        return RegionPrecipitationSeries(series, box, tuple(coverage), self.min_valid_area_fraction)

    def _load_rows_from_ee(self, box: RegionBox, start: date, end: date) -> object:
        ee = self._manager.ee
        geometry = ee.Geometry.Rectangle([box.west, box.south, box.east, box.north], None, False)
        area = ee.Image.pixelArea()

        def attach(image: Any) -> Any:
            rate = image.select(BAND)
            sums = ee.Image.cat([
                rate.multiply(area).rename("weighted"),
                area.updateMask(rate.mask()).rename("valid_area"),
                area.rename("total_area"),
            ]).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=geometry, crs="EPSG:4326",
                crsTransform=IMERG_TRANSFORM, maxPixels=1e8,
            )
            return image.set({
                "month": ee.Date(image.get("system:time_start")).format("YYYY-MM-dd"),
                "weighted": sums.get("weighted"), "valid_area": sums.get("valid_area"),
                "total_area": sums.get("total_area"),
            })

        collection = ee.ImageCollection(DATASET_ID).filterDate(start.isoformat(), end.isoformat())
        return collection.map(attach).reduceColumns(
            ee.Reducer.toList(4), ["month", "weighted", "valid_area", "total_area"]
        ).get("list").getInfo()


class RegionSeriesAdapter:
    """Lets the unchanged PrecipitationService aggregate a pre-fetched regional series."""

    def __init__(self, region: RegionPrecipitationSeries) -> None:
        self._region = region

    def fetch_monthly(self, query: PrecipitationQuery) -> MonthlyPrecipitationSeries:
        return self._region.series
