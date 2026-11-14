from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import (
    get_modis_service,
    get_operation_runner,
    get_settings_dependency,
)
from app.core.config import Settings
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import (
    BoundedOperationRunner,
    OperationBusyError,
    OperationTimeoutError,
)
from app.schemas.ndvi import NDVIQuery, NDVIResponse
from app.services.modis_service import EarthEngineRetrievalError, ModisService


router = APIRouter(prefix="/api/v1", tags=["ndvi"])


def _latest_allowed_end(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(month=2, day=28, year=start.year + years)


@router.get("/ndvi", response_model=NDVIResponse)
async def get_ndvi(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date,
    end_date: date,
    radius_km: Annotated[float, Query(gt=0)] = 5,
    settings: Settings = Depends(get_settings_dependency),
    service: ModisService = Depends(get_modis_service),
    runner: BoundedOperationRunner = Depends(get_operation_runner),
) -> NDVIResponse:
    if start_date >= end_date:
        raise HTTPException(status_code=422, detail="start_date must be before end_date")
    if end_date > _latest_allowed_end(start_date, settings.ndvi_max_date_range_years):
        raise HTTPException(status_code=422, detail="date range exceeds maximum")
    if radius_km > settings.ndvi_max_radius_km:
        raise HTTPException(status_code=422, detail="radius_km exceeds maximum")

    query = NDVIQuery(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
        radius_km=radius_km,
    )
    try:
        return await runner.run(
            lambda: service.fetch_ndvi(query),
            timeout_seconds=settings.ee_request_timeout_seconds,
        )
    except OperationBusyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Earth Engine is busy; retry later",
        ) from exc
    except OperationTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Earth Engine request timed out",
        ) from exc
    except EarthEngineError as exc:
        raise HTTPException(
            status_code=503,
            detail="Earth Engine is unavailable",
        ) from exc
    except EarthEngineRetrievalError as exc:
        raise HTTPException(
            status_code=502,
            detail="Earth Engine data retrieval failed",
        ) from exc

