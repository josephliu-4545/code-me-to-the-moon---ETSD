from collections import OrderedDict
from datetime import date
import math
import time
from threading import Lock
from typing import Any, Callable, Protocol

from app.core.earth_engine import EarthEngineError
from app.precipitation.aggregation import monthly_rate_to_accumulation
from app.precipitation.models import MonthlyPrecipitation, MonthlyPrecipitationSeries, PrecipitationQuery


DATASET_ID = "NASA/GPM_L3/IMERG_MONTHLY_V07"
BAND = "precipitation"
NOMINAL_SCALE_METRES = 11132


class EarthEngineProvider(Protocol):
    ee: Any
    def initialize(self) -> None: ...


class ImergRetrievalError(RuntimeError):
    pass


RowLoader = Callable[[PrecipitationQuery, date, date], object]


def native_grid_cell(latitude: float, longitude: float) -> tuple[str, tuple[float, float]]:
    lon_index = min(3599, max(0, math.floor((longitude + 180) * 10)))
    lat_index = min(1799, max(0, math.floor((latitude + 90) * 10)))
    center_lon = -179.95 + lon_index / 10
    center_lat = -89.95 + lat_index / 10
    return f"imerg-v07:{lat_index}:{lon_index}", (center_lat, center_lon)


class ImergService:
    def __init__(
        self,
        manager: EarthEngineProvider,
        window_years: int = 5,
        cache_max_entries: int = 32,
        cache_ttl_seconds: float = 3600,
        row_loader: RowLoader | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._manager = manager
        self._window_years = window_years
        self._cache_max_entries = cache_max_entries
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock
        self._row_loader = row_loader or self._load_rows_from_ee
        self._cache: OrderedDict[tuple[object, ...], tuple[float, MonthlyPrecipitationSeries]] = OrderedDict()
        self._cache_lock = Lock()

    def fetch_monthly(self, query: PrecipitationQuery) -> MonthlyPrecipitationSeries:
        cell_id, center = native_grid_cell(query.latitude, query.longitude)
        key = (DATASET_ID, "07", "Final", "permanent", cell_id, query.start_date, query.end_date)
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None and self._clock() - cached[0] <= self._cache_ttl_seconds:
                self._cache.move_to_end(key)
                return cached[1]
            if cached is not None:
                del self._cache[key]
        self._manager.initialize()
        rows: list[object] = []
        start = query.start_date
        try:
            while start < query.end_date:
                try:
                    candidate = start.replace(year=start.year + self._window_years)
                except ValueError:
                    candidate = start.replace(year=start.year + self._window_years, day=28)
                end = min(candidate, query.end_date)
                loaded = self._row_loader(query, start, end)
                if not isinstance(loaded, list):
                    raise ImergRetrievalError("malformed IMERG response")
                rows.extend(loaded)
                start = end
            series = self._normalize(rows, cell_id, center)
        except (EarthEngineError, ImergRetrievalError):
            raise
        except Exception as exc:
            raise ImergRetrievalError("Earth Engine IMERG retrieval failed") from exc
        with self._cache_lock:
            self._cache[key] = (self._clock(), series)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max_entries:
                self._cache.popitem(last=False)
        return series

    def _load_rows_from_ee(self, query: PrecipitationQuery, start: date, end: date) -> object:
        ee = self._manager.ee
        point = ee.Geometry.Point([query.longitude, query.latitude])
        collection = ee.ImageCollection(DATASET_ID).filterDate(start.isoformat(), end.isoformat())

        def attach(image: Any) -> Any:
            value = image.select(BAND).reduceRegion(
                reducer=ee.Reducer.first(),
                geometry=point,
                scale=NOMINAL_SCALE_METRES,
                bestEffort=False,
                maxPixels=10,
            ).get(BAND)
            return image.set({
                "month": ee.Date(image.get("system:time_start")).format("YYYY-MM-dd"),
                "rate": value,
            })

        return collection.map(attach).reduceColumns(
            ee.Reducer.toList(2), ["month", "rate"]
        ).get("list").getInfo()

    @staticmethod
    def _normalize(rows: list[object], cell_id: str, center: tuple[float, float]) -> MonthlyPrecipitationSeries:
        observations: list[MonthlyPrecipitation] = []
        seen: set[tuple[int, int]] = set()
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str):
                raise ImergRetrievalError("malformed IMERG row")
            try:
                month = date.fromisoformat(row[0])
            except ValueError as exc:
                raise ImergRetrievalError("invalid IMERG month") from exc
            key = (month.year, month.month)
            if key in seen:
                raise ImergRetrievalError("duplicate IMERG month")
            seen.add(key)
            raw = row[1]
            if raw is None:
                rate = accumulation = None
            elif not isinstance(raw, (int, float)) or not math.isfinite(float(raw)) or float(raw) < 0:
                raise ImergRetrievalError("invalid IMERG precipitation rate")
            else:
                rate = float(raw)
                accumulation = monthly_rate_to_accumulation(rate, month.year, month.month)
            observations.append(MonthlyPrecipitation(date(month.year, month.month, 1), rate, accumulation, True))
        observations.sort(key=lambda item: item.month)
        return MonthlyPrecipitationSeries(tuple(observations), cell_id, center)

