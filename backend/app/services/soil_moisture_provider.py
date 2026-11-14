"""Earth Engine retrieval for GLDAS-2.1 Noah and SMAP L3 Enhanced soil moisture.

Values are sampled from the exact native grid cell that contains the point (no
buffer, no nearest-land substitution). Earth Engine calls are thin loaders that
return raw rows; validation, quality control and normalisation happen here in
Python so they can be tested without Earth Engine.
"""

from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
import math
import time
from threading import Lock
from typing import Any, Callable, Protocol

from app.core.earth_engine import EarthEngineError
from app.soil_moisture.datasets import DatasetDescriptor
from app.soil_moisture.models import CatalogAvailability, MonthlySample


class EarthEngineProvider(Protocol):
    ee: Any
    def initialize(self) -> None: ...


class SoilMoistureRetrievalError(RuntimeError):
    """Malformed, inconsistent or physically invalid provider data (HTTP 502)."""


class UnsupportedLocationError(ValueError):
    """The dataset does not provide values at this location (HTTP 422)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


# Native grids as exposed by Earth Engine (verified live 2026-11-13).
_GRIDS: dict[str, tuple[float, float, float]] = {
    # key: (cell size in degrees, west edge, north edge)
    "gldas": (0.25, -180.0, 90.0),
    "smap": (0.08, -180.0, 85.04450187981062),
}
_FROZEN_KELVIN = 273.15
_FILL_THRESHOLD = -999.0
_SMAP_IMPLAUSIBLE = 0.6
_TSOIL_BAND = "SoilTMP0_10cm_inst"


def _grid_key(descriptor: DatasetDescriptor) -> str:
    return "gldas" if descriptor.is_model else "smap"


@dataclass(frozen=True)
class NativeCell:
    cell_id: str
    center_latitude: float
    center_longitude: float
    south: float
    north: float
    west: float
    east: float
    cell_size_degrees: float
    grid_north_edge: float
    crs: str = "EPSG:4326"

    @property
    def crs_transform(self) -> list[float]:
        return [self.cell_size_degrees, 0, -180.0, 0, -self.cell_size_degrees, self.grid_north_edge]


def native_cell(descriptor: DatasetDescriptor, latitude: float, longitude: float) -> NativeCell:
    size, west, north = _GRIDS[_grid_key(descriptor)]
    cols = round(360 / size)
    col = min(cols - 1, max(0, math.floor((longitude - west) / size)))
    row = max(0, math.floor((north - latitude) / size))
    cell_west = west + col * size
    cell_north = north - row * size
    return NativeCell(
        cell_id=f"{_grid_key(descriptor)}:{row}:{col}",
        center_latitude=round(cell_north - size / 2, 6),
        center_longitude=round(cell_west + size / 2, 6),
        south=round(cell_north - size, 6),
        north=round(cell_north, 6),
        west=round(cell_west, 6),
        east=round(cell_west + size, 6),
        cell_size_degrees=size,
        grid_north_edge=north,
    )


def check_supported(descriptor: DatasetDescriptor, latitude: float, longitude: float) -> None:
    if descriptor.is_model:
        if latitude < -60:
            raise UnsupportedLocationError(
                "outside_dataset_coverage", "GLDAS-2.1 covers 60S-90N; Antarctica is not modelled")
        # Greenland ice sheet: GLDAS documentation advises masking permanently frozen cells.
        if latitude >= 60 and -73 <= longitude <= -12:
            raise UnsupportedLocationError(
                "unsupported_land_cover_region",
                "Greenland ice-sheet cells are not supported for GLDAS soil moisture")
    else:
        north = _GRIDS["smap"][2]
        if not -north <= latitude <= north:
            raise UnsupportedLocationError(
                "outside_dataset_coverage", f"SMAP L3 Enhanced global grid covers {north:.2f}S-{north:.2f}N")


@dataclass(frozen=True)
class ProviderResult:
    samples: tuple[MonthlySample, ...]
    availability: CatalogAvailability
    cell: NativeCell
    valid_cells_in_3x3: int | None
    frozen_months: tuple[date, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


Loader = Callable[..., object]


def _month_starts(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def _windows(start: date, end: date, years: int) -> list[tuple[date, date]]:
    out, s = [], start
    while s < end:
        e = min(date(s.year + years, s.month, 1), end)
        out.append((s, e))
        s = e
    return out


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class EarthEngineSoilMoistureProvider:
    def __init__(
        self,
        manager: EarthEngineProvider,
        window_years: int = 5,
        max_parallel_windows: int = 5,
        smap_window_years: int = 2,
        availability_ttl_seconds: float = 6 * 3600,
        cache_max_entries: int = 32,
        cache_ttl_seconds: float = 3600,
        gldas_loader: Loader | None = None,
        smap_loader: Loader | None = None,
        availability_loader: Loader | None = None,
        neighbourhood_loader: Loader | None = None,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._manager = manager
        self._window_years = window_years
        self._max_parallel = max(1, max_parallel_windows)
        self._smap_window_years = smap_window_years
        self._availability_ttl = availability_ttl_seconds
        self._cache_max = cache_max_entries
        self._cache_ttl = cache_ttl_seconds
        self._gldas_loader = gldas_loader or self._load_gldas_months
        self._smap_loader = smap_loader or self._load_smap_rows
        self._availability_loader = availability_loader or self._load_availability
        self._neighbourhood_loader = neighbourhood_loader or self._load_valid_cells_3x3
        self._clock = clock
        self._today = today
        self._availability: dict[str, tuple[float, CatalogAvailability]] = {}
        self._cache: OrderedDict[tuple, tuple[float, ProviderResult]] = OrderedDict()
        self._lock = Lock()

    # --- public -----------------------------------------------------------------

    def cached_availability(self, descriptor: DatasetDescriptor) -> CatalogAvailability | None:
        """Return a fresh verified catalog entry without initiating provider work."""
        with self._lock:
            hit = self._availability.get(descriptor.collection_ids[0])
            return hit[1] if hit and self._clock() - hit[0] <= self._availability_ttl else None

    def availability(self, descriptor: DatasetDescriptor) -> CatalogAvailability:
        collection = descriptor.collection_ids[0]
        with self._lock:
            hit = self._availability.get(collection)
            if hit and self._clock() - hit[0] <= self._availability_ttl:
                return hit[1]
        self._manager.initialize()
        raw = self._call(self._availability_loader, descriptor)
        if (not isinstance(raw, (list, tuple)) or len(raw) != 2
                or not all(isinstance(x, str) for x in raw)):
            raise SoilMoistureRetrievalError("malformed catalog availability")
        try:
            result = CatalogAvailability(collection, date.fromisoformat(raw[0][:10]),
                                         date.fromisoformat(raw[1][:10]))
        except ValueError as exc:
            raise SoilMoistureRetrievalError("invalid catalog availability") from exc
        with self._lock:
            self._availability[collection] = (self._clock(), result)
        return result

    def fetch(self, descriptor: DatasetDescriptor, latitude: float, longitude: float,
              start: date, end: date) -> ProviderResult:
        check_supported(descriptor, latitude, longitude)
        cell = native_cell(descriptor, latitude, longitude)
        key = (descriptor.key, descriptor.version, cell.cell_id, start, end)
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] <= self._cache_ttl:
                self._cache.move_to_end(key)
                return hit[1]
        availability = self.availability(descriptor)
        fetch_start = max(start, availability.first_image_date.replace(day=1))
        fetch_end = min(end, (availability.last_image_date + timedelta(days=32)).replace(day=1))
        years = self._window_years if descriptor.is_model else self._smap_window_years
        windows = _windows(fetch_start, fetch_end, years) if fetch_start < fetch_end else []
        if descriptor.is_model:
            samples, frozen, diagnostics = self._gldas_samples(descriptor, cell, windows)
        else:
            samples, diagnostics = self._smap_samples(descriptor, cell, windows)
            frozen = ()
        neighbourhood = None
        if windows:
            raw = self._call(self._neighbourhood_loader, descriptor, cell, windows[0][0])
            if raw is not None and (not _finite_number(raw) or not 0 <= raw <= 9):
                raise SoilMoistureRetrievalError("malformed neighbourhood mask count")
            neighbourhood = None if raw is None else int(raw)
        result = ProviderResult(tuple(samples), availability, cell, neighbourhood, tuple(frozen), diagnostics)
        provisional = any(s.nonpermanent_images for s in samples) or (
            fetch_end > (availability.last_image_date - timedelta(days=200)))
        if not provisional:  # recent products may still be revised: never cache them
            with self._lock:
                self._cache[key] = (self._clock(), result)
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
        return result

    # --- normalisation ------------------------------------------------------------

    def _load_windows(self, loader: Loader, descriptor, cell, windows) -> list[object]:
        """Fetch independent windows concurrently; results keep window order."""
        if len(windows) <= 1 or self._max_parallel == 1:
            return [self._call(loader, descriptor, cell, s, e) for s, e in windows]
        with ThreadPoolExecutor(max_workers=min(self._max_parallel, len(windows))) as pool:
            futures = [pool.submit(self._call, loader, descriptor, cell, s, e) for s, e in windows]
            return [f.result() for f in futures]

    def _call(self, loader: Loader, *args: object) -> object:
        try:
            return loader(*args)
        except (EarthEngineError, SoilMoistureRetrievalError, UnsupportedLocationError):
            raise
        except Exception as exc:
            raise SoilMoistureRetrievalError("Earth Engine soil moisture retrieval failed") from exc

    def _gldas_samples(self, descriptor, cell, windows):
        samples, frozen, seen = [], [], set()
        low, high = descriptor.valid_range
        for rows in self._load_windows(self._gldas_loader, descriptor, cell, windows):
            if not isinstance(rows, list):
                raise SoilMoistureRetrievalError("malformed GLDAS response")
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) != 8 or not isinstance(row[0], str):
                    raise SoilMoistureRetrievalError("malformed GLDAS row")
                month_s, images, permanent, status_known, raw, valid, mean, tsoil = row
                try:
                    month = date.fromisoformat(month_s[:10])
                except ValueError as exc:
                    raise SoilMoistureRetrievalError("invalid GLDAS month") from exc
                if month in seen or month.day != 1:
                    raise SoilMoistureRetrievalError("duplicate or misaligned GLDAS month")
                seen.add(month)
                counts = [images, permanent, status_known, raw or 0, valid or 0]
                if not all(_finite_number(c) and c >= 0 and float(c).is_integer() for c in counts):
                    raise SoilMoistureRetrievalError("invalid GLDAS counts")
                images, permanent, status_known, raw, valid = (int(c) for c in counts)
                if raw != valid:
                    raise SoilMoistureRetrievalError(
                        f"GLDAS {month:%Y-%m} has values outside [{low}, {high}] kg m-2")
                if valid == 0:
                    mean = None
                elif not _finite_number(mean):
                    raise SoilMoistureRetrievalError("non-finite GLDAS monthly mean")
                nonpermanent = images - permanent if status_known == images else None
                samples.append(MonthlySample(month, images, valid, None if mean is None else float(mean),
                                             None, nonpermanent))
                if _finite_number(tsoil) and tsoil < _FROZEN_KELVIN:
                    frozen.append(month)
        return samples, frozen, {"frozen_layer_possible_months": len(frozen)}

    def _smap_samples(self, descriptor, cell, windows):
        images_by_month: dict[date, int] = defaultdict(int)
        rows_by_month: dict[date, list[tuple[date, float | None, float | None]]] = defaultdict(list)
        seen_images: set[date] = set()
        seen_rows: set[date] = set()
        for payload in self._load_windows(self._smap_loader, descriptor, cell, windows):
            if (not isinstance(payload, dict) or not isinstance(payload.get("images"), list)
                    or not isinstance(payload.get("rows"), list)):
                raise SoilMoistureRetrievalError("malformed SMAP response")
            for image_day in payload["images"]:
                day = self._day(image_day)
                if day in seen_images:
                    raise SoilMoistureRetrievalError("duplicate SMAP image date")
                seen_images.add(day)
                images_by_month[day.replace(day=1)] += 1
            for row in payload["rows"]:
                if not isinstance(row, (list, tuple)) or len(row) != 3:
                    raise SoilMoistureRetrievalError("malformed SMAP row")
                day = self._day(row[0])
                if day in seen_rows or day not in seen_images:
                    raise SoilMoistureRetrievalError("duplicate or orphan SMAP row")
                seen_rows.add(day)
                rows_by_month[day.replace(day=1)].append((day, row[1], row[2]))
        stats = defaultdict(int)
        samples = []
        for month in sorted(images_by_month):
            valid_days, values = [], []
            for day, value, flag in rows_by_month.get(month, []):
                if flag is not None:
                    stats["observation_opportunities"] += 1
                if _finite_number(value) and value <= _FILL_THRESHOLD:
                    stats["fill_value_leaks"] += 1
                    continue
                if not (_finite_number(value) and _finite_number(flag)):
                    continue
                if flag != 0:
                    stats["qc_rejected_retrievals"] += 1
                    continue
                if not 0 <= value <= 1:
                    stats["out_of_range_values"] += 1
                    continue
                if value > _SMAP_IMPLAUSIBLE:
                    stats["values_above_0_6"] += 1
                valid_days.append(day)
                values.append(float(value))
            samples.append(MonthlySample(
                month, images_by_month[month], len(values),
                sum(values) / len(values) if values else None, tuple(valid_days)))
        stats["valid_retrievals"] = sum(s.valid_values for s in samples)
        return samples, dict(stats)

    @staticmethod
    def _day(value: object) -> date:
        if not isinstance(value, str):
            raise SoilMoistureRetrievalError("invalid SMAP date")
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise SoilMoistureRetrievalError("invalid SMAP date") from exc

    # --- Earth Engine loaders (exercised by live validation) ------------------------

    def _point(self, cell: NativeCell):
        return self._manager.ee.Geometry.Point([cell.center_longitude, cell.center_latitude])

    def _load_availability(self, descriptor: DatasetDescriptor) -> list[str]:
        ee = self._manager.ee
        coll = ee.ImageCollection(descriptor.collection_ids[0])
        first_doc = descriptor.documented_first_date
        head = coll.filterDate((first_doc - timedelta(days=60)).isoformat(),
                               (first_doc + timedelta(days=400)).isoformat())
        tail_end = descriptor.documented_last_date or self._today()
        tail = coll.filterDate((tail_end - timedelta(days=400)).isoformat(),
                               (tail_end + timedelta(days=2)).isoformat())
        return ee.List([
            ee.Date(head.aggregate_min("system:time_start")).format("YYYY-MM-dd"),
            ee.Date(tail.aggregate_max("system:time_start")).format("YYYY-MM-dd"),
        ]).getInfo()

    def _load_gldas_months(self, descriptor, cell, start: date, end: date) -> object:
        ee = self._manager.ee
        point = self._point(cell)
        band = descriptor.band
        coll = ee.ImageCollection(descriptor.collection_ids[0]).filterDate(
            start.isoformat(), end.isoformat()).select([band, _TSOIL_BAND])
        low, high = descriptor.valid_range
        starts = ee.List([m.isoformat() for m in _month_starts(start, end)])

        def per_month(month_iso):
            m = ee.Date(month_iso)
            c = coll.filterDate(m, m.advance(1, "month"))
            sm = c.select(band)
            in_range = sm.map(lambda im: im.updateMask(im.gte(low).And(im.lte(high))))
            stats = ee.Image.cat([
                sm.count().rename("raw"), in_range.count().rename("valid"),
                in_range.mean().rename("mean"), c.select(_TSOIL_BAND).mean().rename("tsoil"),
            ]).reduceRegion(ee.Reducer.first(), point, crs=cell.crs, crsTransform=cell.crs_transform)
            size = c.size()
            return ee.Algorithms.If(size.gt(0), ee.List([
                month_iso, size, c.filter(ee.Filter.eq("status", "permanent")).size(),
                c.filter(ee.Filter.notNull(["status"])).size(),
                stats.get("raw"), stats.get("valid"), stats.get("mean"), stats.get("tsoil"),
            ]), ee.List([month_iso, 0, 0, 0, 0, 0, None, None]))

        return starts.map(per_month).getInfo()

    def _load_smap_rows(self, descriptor, cell, start: date, end: date) -> object:
        ee = self._manager.ee
        point = self._point(cell)
        sm, qc = descriptor.band, descriptor.qc_band
        coll = ee.ImageCollection(descriptor.collection_ids[0]).filterDate(
            start.isoformat(), end.isoformat()).select([sm, qc])

        def row(im):
            values = im.reduceRegion(ee.Reducer.first(), point, crs=cell.crs, crsTransform=cell.crs_transform)
            return ee.Feature(None, values.set("date", im.date().format("YYYY-MM-dd")))

        dates = coll.aggregate_array("system:time_start").map(
            lambda t: ee.Date(t).format("YYYY-MM-dd"))
        rows = ee.FeatureCollection(coll.map(row)).filter(ee.Filter.notNull([qc])).reduceColumns(
            ee.Reducer.toList(3), ["date", sm, qc]).get("list")
        return ee.Dictionary({"images": dates, "rows": rows}).getInfo()

    def _load_valid_cells_3x3(self, descriptor, cell, month: date) -> object:
        ee = self._manager.ee
        size = cell.cell_size_degrees
        box = ee.Geometry.Rectangle(
            [cell.west - size + size / 4, cell.south - size + size / 4,
             cell.east + size - size / 4, cell.north + size - size / 4], None, False)
        band = descriptor.qc_band or descriptor.band
        coll = ee.ImageCollection(descriptor.collection_ids[0]).filterDate(
            month.isoformat(), (month + timedelta(days=32)).replace(day=1).isoformat()).select(band)
        presence = coll.count().gt(0).selfMask()
        return presence.reduceRegion(ee.Reducer.count(), box, crs=cell.crs,
                                     crsTransform=cell.crs_transform).get(band).getInfo()
