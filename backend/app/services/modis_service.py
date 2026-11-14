from datetime import date, datetime, timedelta, timezone
import math
from typing import Any, Protocol

from app.core.earth_engine import EarthEngineError
from app.schemas.ndvi import (
    NDVILocation,
    NDVIObservation,
    NDVIPeriod,
    NDVIQuery,
    NDVIResponse,
)
from app.statistics.models import ObservationSeries, TimedValue, YearCoverage


DATASET_ID = "MODIS/061/MOD13Q1"
SCALE_FACTOR = 0.0001
REDUCTION_SCALE_METRES = 250


class EarthEngineProvider(Protocol):
    ee: Any

    def initialize(self) -> None: ...


class EarthEngineRetrievalError(RuntimeError):
    pass


def apply_good_quality_mask(image: Any) -> Any:
    quality_mask = image.select("SummaryQA").eq(0)
    return (
        image.select("NDVI")
        .updateMask(quality_mask)
        .multiply(SCALE_FACTOR)
        .rename("ndvi")
    )


def build_good_quality_support(image: Any) -> Any:
    """Build a binary support raster on the native MODIS image grid.

    Values are 1 only where SummaryQA is good and the NDVI band is present.
    Unmasking to zero makes the sum the valid-pixel count and the count the
    total sampled-pixel count when both are reduced together.
    """
    return (
        image.select("SummaryQA")
        .eq(0)
        .And(image.select("NDVI").mask())
        .unmask(0)
        .rename("support")
    )


def calculate_spatial_coverage_percentage(
    valid_pixels: int | float,
    total_pixels: int | float,
) -> float | None:
    """Return bounded spatial support, or None for an empty sampling grid."""
    valid = float(valid_pixels)
    total = float(total_pixels)
    if valid < 0 or total < 0:
        raise ValueError("pixel counts cannot be negative")
    if total == 0:
        if valid == 0:
            return None
        raise ValueError("valid pixels cannot exist with a zero denominator")
    if valid > total:
        raise ValueError("valid pixels cannot exceed total pixels")
    return valid / total * 100


class ModisService:
    def __init__(self, manager: EarthEngineProvider) -> None:
        self._manager = manager

    def fetch_ndvi(self, query: NDVIQuery) -> NDVIResponse:
        self._manager.initialize()
        ee = self._manager.ee

        try:
            region = ee.Geometry.Point([query.longitude, query.latitude]).buffer(
                query.radius_km * 1000
            )
            collection = ee.ImageCollection(DATASET_ID).filterDate(
                query.start_date.isoformat(),
                query.end_date.isoformat(),
            )

            def attach_observation(image: Any) -> Any:
                ndvi = apply_good_quality_mask(image)
                regional_mean = ndvi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=region,
                    scale=REDUCTION_SCALE_METRES,
                    bestEffort=False,
                    maxPixels=1_000_000,
                ).get("ndvi")
                return image.set(
                    {
                        "date": ee.Date(image.get("system:time_start")).format(
                            "YYYY-MM-dd"
                        ),
                        "ndvi": regional_mean,
                    }
                )

            rows = (
                collection.map(attach_observation)
                .filter(ee.Filter.notNull(["ndvi"]))
                .reduceColumns(ee.Reducer.toList(2), ["date", "ndvi"])
                .get("list")
                .getInfo()
            )
        except EarthEngineError:
            raise
        except Exception as exc:
            raise EarthEngineRetrievalError(
                "Earth Engine NDVI retrieval failed"
            ) from exc

        observations = self._normalize_rows(rows)
        return NDVIResponse(
            location=NDVILocation(
                latitude=query.latitude,
                longitude=query.longitude,
                radius_km=query.radius_km,
            ),
            period=NDVIPeriod(start=query.start_date, end=query.end_date),
            observation_count=len(observations),
            observations=observations,
        )

    def fetch_ndvi_series(self, query: NDVIQuery) -> ObservationSeries:
        self._manager.initialize()
        ee = self._manager.ee
        try:
            region = ee.Geometry.Point([query.longitude, query.latitude]).buffer(
                query.radius_km * 1000
            )
            collection = ee.ImageCollection(DATASET_ID).filterDate(
                query.start_date.isoformat(), query.end_date.isoformat()
            )
            available_timestamps = collection.aggregate_array(
                "system:time_start"
            ).getInfo()
            support_reducer = ee.Reducer.sum().combine(
                reducer2=ee.Reducer.count(), sharedInputs=True
            )

            def attach_metrics(image: Any) -> Any:
                ndvi = apply_good_quality_mask(image)
                metrics = ndvi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=region,
                    scale=REDUCTION_SCALE_METRES,
                    bestEffort=False,
                    maxPixels=1_000_000,
                )
                support_metrics = build_good_quality_support(image).reduceRegion(
                    reducer=support_reducer,
                    geometry=region,
                    scale=REDUCTION_SCALE_METRES,
                    bestEffort=False,
                    maxPixels=1_000_000,
                )
                return image.set(
                    {
                        "date": ee.Date(image.get("system:time_start")).format(
                            "YYYY-MM-dd"
                        ),
                        "ndvi": metrics.get("ndvi"),
                        "valid_pixels": support_metrics.get("support_sum"),
                        "total_pixels": support_metrics.get("support_count"),
                    }
                )

            valid_rows = (
                collection.map(attach_metrics)
                .filter(ee.Filter.notNull(["ndvi", "valid_pixels", "total_pixels"]))
                .reduceColumns(
                    ee.Reducer.toList(4),
                    ["date", "ndvi", "valid_pixels", "total_pixels"],
                )
                .get("list")
                .getInfo()
            )
        except EarthEngineError:
            raise
        except Exception as exc:
            raise EarthEngineRetrievalError(
                "Earth Engine NDVI series retrieval failed"
            ) from exc

        valid_by_date = {
            str(row[0]): row
            for row in valid_rows or []
            if isinstance(row, (list, tuple)) and len(row) == 4
        }
        rows: list[list[object]] = []
        for timestamp in available_timestamps or []:
            day = datetime.fromtimestamp(float(timestamp) / 1000, tz=timezone.utc).date()
            rows.append(valid_by_date.get(day.isoformat(), [day.isoformat(), None, 0, None]))
        return self._series_from_rows(query, rows)

    @staticmethod
    def _nominal_slots(year: int) -> tuple[date, ...]:
        first = date(year, 1, 1)
        return tuple(first + timedelta(days=16 * index) for index in range(23))

    @classmethod
    def _series_from_rows(
        cls,
        query: NDVIQuery,
        rows: object,
    ) -> ObservationSeries:
        if not isinstance(rows, list):
            rows = []
        available_by_year: dict[int, list[date]] = {}
        observations: list[TimedValue] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 4:
                continue
            raw_date, raw_value, raw_valid, raw_total = row
            if not isinstance(raw_date, str):
                continue
            try:
                day = date.fromisoformat(raw_date)
            except ValueError:
                continue
            available_by_year.setdefault(day.year, []).append(day)
            if raw_value is None:
                continue
            if not all(isinstance(value, (int, float)) for value in (raw_value, raw_valid, raw_total)):
                raise ValueError("pixel metrics must be numeric")
            valid_pixels, total_pixels = int(raw_valid), int(raw_total)
            spatial_coverage = calculate_spatial_coverage_percentage(
                valid_pixels, total_pixels
            )
            observations.append(
                TimedValue(
                    date=day,
                    value=float(raw_value),
                    spatial_coverage_percentage=spatial_coverage,
                    valid_pixel_count=valid_pixels if spatial_coverage is not None else None,
                    total_pixel_count=total_pixels if spatial_coverage is not None else None,
                )
            )

        last_inclusive = query.end_date - timedelta(days=1)
        coverage: list[YearCoverage] = []
        for year in range(query.start_date.year, last_inclusive.year + 1):
            expected = cls._nominal_slots(year)
            available = tuple(sorted(available_by_year.get(year, [])))
            complete = (
                query.start_date <= date(year, 1, 1)
                and query.end_date >= date(year + 1, 1, 1)
            )
            coverage.append(
                YearCoverage(
                    year=year,
                    expected_slot_dates=expected,
                    available_image_dates=available,
                    is_complete_calendar_year=complete,
                )
            )
        return ObservationSeries(
            variable="NDVI",
            value_units="NDVI units",
            dataset="NASA MODIS MOD13Q1.061",
            observations=tuple(sorted(observations, key=lambda item: item.date)),
            coverage_by_year=tuple(coverage),
        )

    @staticmethod
    def _normalize_rows(rows: object) -> list[NDVIObservation]:
        if not isinstance(rows, list):
            return []

        observations: list[NDVIObservation] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                continue
            raw_date, raw_value = row
            if not isinstance(raw_date, str) or not isinstance(raw_value, (int, float)):
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                continue
            try:
                observation_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            observations.append(NDVIObservation(date=observation_date, ndvi=value))

        observations.sort(key=lambda observation: observation.date)
        return observations

