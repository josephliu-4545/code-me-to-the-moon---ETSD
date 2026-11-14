from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import (
    get_ndvi_trend_service,
    get_operation_runner,
    get_settings_dependency,
)
from app.api.routes.ndvi import _latest_allowed_end
from app.core.config import Settings
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import BoundedOperationRunner, OperationBusyError, OperationTimeoutError
from app.schemas.ndvi import NDVIQuery
from app.schemas.trend import NDVITrendResponse
from app.services.modis_service import EarthEngineRetrievalError
from app.services.ndvi_trend_service import NDVITrendService


router = APIRouter(prefix="/api/v1", tags=["ndvi-trend"])


@router.get("/ndvi/trend", response_model=NDVITrendResponse)
async def get_ndvi_trend(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date,
    end_date: date,
    radius_km: Annotated[float, Query(gt=0)] = 5,
    settings: Settings = Depends(get_settings_dependency),
    service: NDVITrendService = Depends(get_ndvi_trend_service),
    runner: BoundedOperationRunner = Depends(get_operation_runner),
) -> NDVITrendResponse:
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
            lambda: service.analyze(query),
            timeout_seconds=settings.ee_request_timeout_seconds,
        )
    except OperationBusyError as exc:
        raise HTTPException(status_code=503, detail="Earth Engine is busy; retry later") from exc
    except OperationTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Earth Engine request timed out") from exc
    except EarthEngineError as exc:
        raise HTTPException(status_code=503, detail="Earth Engine is unavailable") from exc
    except EarthEngineRetrievalError as exc:
        raise HTTPException(status_code=502, detail="Earth Engine data retrieval failed") from exc

