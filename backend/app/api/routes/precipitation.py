from dataclasses import asdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_operation_runner, get_precipitation_service, get_settings_dependency
from app.core.config import Settings
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import BoundedOperationRunner, OperationBusyError, OperationTimeoutError
from app.precipitation.models import PrecipitationQuery
from app.schemas.precipitation import PrecipitationResponse, PrecipitationTrendResponse
from app.services.imerg_service import ImergRetrievalError
from app.services.precipitation_service import PrecipitationAnalysis, PrecipitationService


router = APIRouter(prefix="/api/v1", tags=["precipitation"])


def _latest_allowed_end(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, month=2, day=28)


def _query(latitude: float, longitude: float, start_date: date, end_date: date, settings: Settings) -> PrecipitationQuery:
    if start_date >= end_date:
        raise HTTPException(422, "start_date must be before end_date")
    if end_date > _latest_allowed_end(start_date, settings.precipitation_max_date_range_years):
        raise HTTPException(422, "date range exceeds maximum")
    return PrecipitationQuery(latitude, longitude, start_date, end_date)


def _base(query: PrecipitationQuery, result: PrecipitationAnalysis, temporal_resolution: str) -> dict:
    series = result.series
    monthly = [
        {
            "month": item.month,
            "mean_rate_mm_per_hour": item.mean_rate_mm_per_hour,
            "accumulation_mm": item.accumulation_mm,
            "catalog_available": item.catalog_available,
            "version": item.version,
            "run": item.run,
            "status": item.status,
        }
        for item in series.observations
    ]
    annual = [asdict(item) for item in result.annual_summaries]
    valid = sum(item.valid_months for item in result.annual_summaries)
    expected = sum(item.expected_months for item in result.annual_summaries)
    return {
        "variable": "Precipitation",
        "dataset": {
            "source": "NASA GPM IMERG",
            "id": "NASA/GPM_L3/IMERG_MONTHLY_V07",
            "version": "07",
            "product": "3IMERGM",
            "run": "Final",
            "status": "permanent",
            "doi": "10.5067/GPM/IMERG/3B-MONTH/07",
        },
        "location": {"latitude": query.latitude, "longitude": query.longitude},
        "spatial_support": {
            "type": "native_grid_cell",
            "grid_cell_id": series.grid_cell_id,
            "grid_cell_center": series.grid_cell_center,
            "projection": series.projection,
            "grid_spacing_degrees": series.grid_spacing_degrees,
            "nominal_pixel_size_metres": series.nominal_pixel_size_metres,
        },
        "period": {"start": query.start_date, "end_exclusive": query.end_date},
        "temporal_resolution": temporal_resolution,
        "units": {"source_rate": "mm/hour", "monthly_accumulation": "mm/month", "annual_accumulation": "mm/year", "trend": "mm/year²"},
        "monthly_observations": monthly if temporal_resolution == "monthly" else [],
        "annual_summaries": annual if temporal_resolution == "annual" else [],
        "coverage": {"expected_months": expected, "valid_months": valid, "coverage_percentage": valid / expected * 100 if expected else 0},
        "methodology": {
            "conversion": "monthly mean rate × 24 × actual calendar days",
            "annual_aggregation": "sum of twelve valid monthly accumulations",
            "trend_input": "complete eligible annual accumulations",
            "missing_values": "retained as missing; never interpreted as zero or interpolated",
        },
        "limitations": [
            "IMERG is a satellite-gauge gridded estimate, not a rain-gauge measurement or administrative-region average.",
            "The 0.1 degree native grid is not 5 km spatial resolution.",
            "Monthly products support accumulation analysis, not precipitation intensity or event extremes.",
            "Monthly availability does not prove completeness of every underlying half-hour interval.",
            "Version 07 is pinned and is not mixed with Version 08.",
        ],
    }


async def _run(runner, settings, operation):
    try:
        return await runner.run(operation, timeout_seconds=settings.ee_request_timeout_seconds)
    except OperationBusyError as exc:
        raise HTTPException(503, "Earth Engine is busy; retry later") from exc
    except OperationTimeoutError as exc:
        raise HTTPException(504, "Earth Engine request timed out") from exc
    except EarthEngineError as exc:
        raise HTTPException(503, "Earth Engine is unavailable") from exc
    except ImergRetrievalError as exc:
        raise HTTPException(502, "Earth Engine data retrieval failed") from exc


@router.get("/precipitation", response_model=PrecipitationResponse)
async def precipitation(
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date, temporal_resolution: Literal["monthly", "annual"] = "monthly",
    settings: Settings = Depends(get_settings_dependency), service: PrecipitationService = Depends(get_precipitation_service),
    runner: BoundedOperationRunner = Depends(get_operation_runner),
):
    query = _query(latitude, longitude, start_date, end_date, settings)
    result = await _run(runner, settings, lambda: service.analyze(query))
    return _base(query, result, temporal_resolution)


@router.get("/precipitation/trend", response_model=PrecipitationTrendResponse)
async def precipitation_trend(
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date, include_relative_change: bool = False,
    settings: Settings = Depends(get_settings_dependency), service: PrecipitationService = Depends(get_precipitation_service),
    runner: BoundedOperationRunner = Depends(get_operation_runner),
):
    query = _query(latitude, longitude, start_date, end_date, settings)
    result = await _run(runner, settings, lambda: service.analyze(query, include_relative_change))
    payload = _base(query, result, "annual")
    trend = asdict(result.trend)
    trend["annual_total_change_mm_per_calendar_year"] = result.annual_total_change_mm_per_calendar_year
    trend["slope_units"] = "mm/year²"
    payload["trend"] = trend
    payload["relative_change"] = None if result.relative_change_percent_per_year is None else {
        "percent_of_reference_per_year": result.relative_change_percent_per_year,
        "reference_median_annual_total_mm": result.relative_reference_median_mm,
        "method": "Theil-Sen slope divided by median eligible annual total",
    }
    return payload

