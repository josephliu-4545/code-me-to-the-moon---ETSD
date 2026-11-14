from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.scientific_notes import TREND_METHOD
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import OperationBusyError, OperationTimeoutError
from app.precipitation.models import PrecipitationPolicy, PrecipitationQuery
from app.services.imerg_region_service import RegionBox, RegionSeriesAdapter
from app.services.imerg_service import ImergRetrievalError
from app.services.precipitation_service import PrecipitationService


router = APIRouter(prefix="/api/v1", tags=["precipitation"])


@router.get("/precipitation/region/trend")
async def precipitation_region_trend(
    request: Request,
    west: Annotated[float, Query(ge=-180, le=180)], south: Annotated[float, Query(ge=-90, le=90)],
    east: Annotated[float, Query(ge=-180, le=180)], north: Annotated[float, Query(ge=-90, le=90)],
    start_date: date, end_date: date,
) -> dict[str, Any]:
    settings = request.app.state.settings
    try:
        box = RegionBox(west, south, east, north)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    limit = settings.precipitation_region_max_span_degrees
    if box.width > limit or box.height > limit:
        raise HTTPException(422, f"region must be at most {limit} degrees wide and tall")
    if box.width < 0.1 or box.height < 0.1:
        raise HTTPException(422, "region must be at least 0.1 degrees (one IMERG cell) wide and tall")
    if start_date >= end_date:
        raise HTTPException(422, "start_date must be before end_date")
    try:
        latest = start_date.replace(year=start_date.year + settings.precipitation_max_date_range_years)
    except ValueError:
        latest = start_date.replace(year=start_date.year + settings.precipitation_max_date_range_years, day=28)
    if end_date > latest:
        raise HTTPException(422, "date range exceeds maximum")

    region_service = request.app.state.imerg_region_service
    runner = request.app.state.operation_runner
    center_lat, center_lon = box.center
    query = PrecipitationQuery(center_lat, center_lon, start_date, end_date)

    def run():
        region = region_service.fetch_region(box, start_date, end_date)
        analysis = PrecipitationService(
            RegionSeriesAdapter(region),
            PrecipitationPolicy(minimum_valid_months=settings.precipitation_min_valid_months),
        ).analyze(query)
        return region, analysis

    try:
        region, analysis = await runner.run(run, timeout_seconds=settings.ee_request_timeout_seconds)
    except OperationBusyError as exc:
        raise HTTPException(503, "Earth Engine is busy; retry later") from exc
    except OperationTimeoutError as exc:
        raise HTTPException(504, "Earth Engine request timed out") from exc
    except EarthEngineError as exc:
        raise HTTPException(503, "Earth Engine is unavailable") from exc
    except ImergRetrievalError as exc:
        raise HTTPException(502, "Earth Engine data retrieval failed") from exc

    accepted = sum(1 for c in region.coverage if c.accepted)
    return {
        "variable": "Precipitation",
        "dataset": {"source": "NASA GPM IMERG", "id": "NASA/GPM_L3/IMERG_MONTHLY_V07", "version": "07",
                    "run": "Final", "doi": "10.5067/GPM/IMERG/3B-MONTH/07"},
        "spatial_support": {
            "type": "bbox_area_weighted_mean",
            "bbox": asdict(box),
            "description": "Area-weighted mean over valid 0.1-degree IMERG pixels inside the box (pixel areas from Earth Engine; partial edge pixels weighted by overlap)",
            "native_grid_degrees": 0.1,
            "min_valid_area_fraction": region.min_valid_area_fraction,
            "single_cell_substituted": False,
        },
        "period": {"start": start_date, "end_exclusive": end_date},
        "units": {"monthly_accumulation": "mm/month", "annual_accumulation": "mm/year", "trend": "mm/year²"},
        "monthly_coverage": [asdict(c) for c in region.coverage],
        "coverage": {"months": len(region.coverage), "months_meeting_area_threshold": accepted},
        "annual_summaries": [asdict(s) for s in analysis.annual_summaries],
        "trend": asdict(analysis.trend),
        "methodology": {
            "regional_mean": "sum(rate x pixel area) / sum(valid pixel area) for each monthly image",
            "month_validity": f"a month counts only if valid pixel area is at least {region.min_valid_area_fraction:.0%} of the box area (project policy, not a universal standard)",
            "conversion": "regional mean rate x 24 x calendar days",
            "annual_aggregation": "sum of twelve valid monthly accumulations",
            "missing_values": "retained as missing; never zero or interpolated",
            "trend_method": TREND_METHOD,
        },
        "limitations": [
            "A regional mean smooths local extremes; it is not the precipitation at any single place inside the box.",
            "IMERG is a satellite-gauge gridded estimate, not a rain-gauge network average.",
            "Box edges follow latitude and longitude lines; areas are true pixel areas, so high-latitude boxes are not distorted.",
            "Boxes crossing the antimeridian and arbitrary polygons are not yet supported.",
            "Version 07 is pinned and not mixed with other versions.",
        ],
    }
