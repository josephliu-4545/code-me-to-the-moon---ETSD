from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_power_operation_runner, get_relative_humidity_service, get_settings_dependency
from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner, OperationBusyError, OperationTimeoutError
from app.power.client import PowerClientError, PowerRateLimitError, PowerTimeoutError, PowerUpstreamValidationError
from app.power.models import PowerPointQuery
from app.schemas.relative_humidity import RelativeHumidityResponse, RelativeHumidityTrendResponse
from app.services.relative_humidity_service import RelativeHumidityDataError, RelativeHumidityService


router = APIRouter(prefix="/api/v1", tags=["relative-humidity"])


def _validate_dates(start: date, end: date, settings: Settings) -> None:
    if start >= end:
        raise HTTPException(422, "start_date must be before end_date")
    if start < date(1981, 1, 1):
        raise HTTPException(422, "NASA POWER data begins on 1981-01-01")
    try:
        maximum = start.replace(year=start.year + settings.power_max_date_range_years)
    except ValueError:
        maximum = start.replace(month=2, day=28, year=start.year + settings.power_max_date_range_years)
    if end > maximum:
        raise HTTPException(422, "date range exceeds maximum")


def _period_end(day: date, resolution: str) -> date:
    if resolution == "daily":
        return day + timedelta(days=1)
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def _base(query: PowerPointQuery) -> dict:
    return {
        "location": {"latitude": query.latitude, "longitude": query.longitude, "spatial_representation": "NASA POWER grid-cell estimate", "native_grid": "0.5 x 0.625 degrees"},
        "period": {"start": query.start_date, "end": query.end_date},
        "limitations": [
            "Values are gridded meteorological estimates, not station observations or administrative-region averages.",
            "Local Solar Time (LST) is solar time and must not be interpreted as the location's civil time zone.",
            "Recent near-real-time meteorological values may later be replaced by climate-quality products.",
        ],
    }


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, (OperationTimeoutError, PowerTimeoutError)):
        raise HTTPException(504, "NASA POWER request timed out") from exc
    if isinstance(exc, (OperationBusyError, PowerRateLimitError)):
        raise HTTPException(503, "NASA POWER is busy; retry later") from exc
    if isinstance(exc, (PowerClientError, RelativeHumidityDataError, PowerUpstreamValidationError)):
        raise HTTPException(502, "NASA POWER data retrieval failed") from exc
    raise exc


@router.get("/relative-humidity", response_model=RelativeHumidityResponse)
async def get_relative_humidity(
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date,
    temporal_resolution: Literal["daily", "monthly"] = "daily",
    time_standard: Literal["LST", "UTC"] = "LST",
    settings: Settings = Depends(get_settings_dependency), service: RelativeHumidityService = Depends(get_relative_humidity_service),
    runner: BoundedOperationRunner = Depends(get_power_operation_runner),
) -> dict:
    _validate_dates(start_date, end_date, settings)
    query = PowerPointQuery(latitude, longitude, start_date, end_date, time_standard)
    try:
        series = await runner.run(lambda: service.fetch_daily(query) if temporal_resolution == "daily" else service.fetch_monthly(query), settings.power_request_timeout_seconds)
    except Exception as exc:
        _raise_http(exc)
    base = _base(query)
    return {
        **base, "temporal_resolution": temporal_resolution, "time_standard": series.time_standard,
        "observations": [{"period_start": item.date, "period_end": _period_end(item.date, temporal_resolution), "relative_humidity_percent": item.value} for item in series.observations],
        "coverage": {"expected": series.expected_count, "returned": series.returned_count, "valid": series.valid_count, "missing": len(series.missing_dates), "valid_percentage": series.valid_count / series.expected_count * 100 if series.expected_count else 0},
        "methodology": {"missing_values": "excluded without interpolation", "spatial_basis": "single source grid cell"},
    }


@router.get("/relative-humidity/trend", response_model=RelativeHumidityTrendResponse)
async def get_relative_humidity_trend(
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)], start_date: date, end_date: date,
    settings: Settings = Depends(get_settings_dependency), service: RelativeHumidityService = Depends(get_relative_humidity_service), runner: BoundedOperationRunner = Depends(get_power_operation_runner),
) -> dict:
    _validate_dates(start_date, end_date, settings)
    query = PowerPointQuery(latitude, longitude, start_date, end_date, "LST")
    try:
        result = await runner.run(lambda: service.analyze(query), settings.power_request_timeout_seconds)
    except Exception as exc:
        _raise_http(exc)
    trend = asdict(result.trend)
    trend["excluded_years"] = [{"year": year, "reasons": list(reasons)} for year, reasons in result.trend.excluded_years]
    base = _base(query)
    annual_summaries = []
    for item in result.annual_summaries:
        summary = asdict(item)
        summary["returned_observations"] = summary.pop("available_images")
        summary.pop("image_availability_percentage")
        summary.pop("minimum_spatial_coverage_percentage")
        summary.pop("mean_spatial_coverage_percentage")
        summary.pop("median_spatial_coverage_percentage")
        summary.pop("spatial_coverage_threshold_applied")
        annual_summaries.append(summary)
    return {
        **base, "time_standard": result.series.time_standard, "annual_summaries": annual_summaries, "trend": trend,
        "coverage_policy": {"complete_calendar_years": True, "required_months": 12, "minimum_annual_daily_coverage": settings.rh_min_annual_coverage, "minimum_monthly_daily_coverage": settings.rh_min_monthly_coverage, "policy_status": "application-defined scientific screening policy"},
        "methodology": {"monthly_aggregation": "arithmetic mean of valid daily RH2M observations", "annual_aggregation": "equal-weighted mean of valid monthly means", "missing_values": "excluded without interpolation", "trend_input": "daily RH2M in LST"},
    }
