from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_power_operation_runner, get_settings_dependency, get_temperature_service
from app.api.routes.relative_humidity import _base, _raise_http, _validate_dates
from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner
from app.power.models import PowerPointQuery
from app.services.temperature_service import TemperatureService
from app.schemas.temperature import TemperatureResponse, TemperatureTrendResponse

router=APIRouter(prefix="/api/v1",tags=["temperature"])

@router.get("/temperature",response_model=TemperatureResponse)
async def temperature(latitude:Annotated[float,Query(ge=-90,le=90)],longitude:Annotated[float,Query(ge=-180,le=180)],start_date:date,end_date:date,temporal_resolution:Literal["daily","monthly"]="daily",time_standard:Literal["LST","UTC"]="LST",settings:Settings=Depends(get_settings_dependency),service:TemperatureService=Depends(get_temperature_service),runner:BoundedOperationRunner=Depends(get_power_operation_runner)):
    _validate_dates(start_date,end_date,settings); query=PowerPointQuery(latitude,longitude,start_date,end_date,time_standard)
    try: series=await runner.run(lambda: service.fetch_daily(query) if temporal_resolution=="daily" else service.fetch_monthly(query),settings.power_request_timeout_seconds)
    except Exception as exc: _raise_http(exc)
    base=_base(query)
    return {**base,"variable":"Air Temperature","dataset":"NASA POWER","parameter":"T2M","units":"°C","time_standard":series.time_standard,"temporal_resolution":temporal_resolution,"observations":[{"period_start":x.date,"temperature_celsius":x.value} for x in series.observations],"coverage":{"expected":series.expected_count,"returned":series.returned_count,"valid":len(series.observations),"missing":len(series.missing_dates)}}

@router.get("/temperature/trend",response_model=TemperatureTrendResponse)
async def temperature_trend(latitude:Annotated[float,Query(ge=-90,le=90)],longitude:Annotated[float,Query(ge=-180,le=180)],start_date:date,end_date:date,settings:Settings=Depends(get_settings_dependency),service:TemperatureService=Depends(get_temperature_service),runner:BoundedOperationRunner=Depends(get_power_operation_runner)):
    _validate_dates(start_date,end_date,settings); query=PowerPointQuery(latitude,longitude,start_date,end_date,"LST")
    try: result=await runner.run(lambda:service.analyze(query),settings.power_request_timeout_seconds)
    except Exception as exc: _raise_http(exc)
    trend=asdict(result.trend); ts=result.trend.theil_sen
    trend["slope_celsius_per_decade"]=ts.slope*10 if ts else None
    trend["confidence_interval_celsius_per_decade"]=[x*10 for x in ts.confidence_interval] if ts and ts.confidence_interval else None
    return {**_base(query),"variable":"Air Temperature","dataset":"NASA POWER","parameter":"T2M","units":"°C","time_standard":result.series.time_standard,"annual_summaries":[asdict(x) for x in result.annual_summaries],"trend":trend,"methodology":{"annual_aggregation":"equal-weighted mean of valid monthly means","trend_input":"daily T2M in LST"}}
