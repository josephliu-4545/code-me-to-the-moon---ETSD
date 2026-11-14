from dataclasses import asdict
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends,Query

from app.api.dependencies import get_extreme_heat_service,get_power_operation_runner,get_settings_dependency
from app.api.routes.relative_humidity import _base,_raise_http,_validate_dates
from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner
from app.power.models import PowerPointQuery
from app.services.extreme_heat_service import ExtremeHeatService
from app.schemas.extreme_heat import ExtremeHeatResponse

router=APIRouter(prefix="/api/v1",tags=["extreme-heat"])

async def _analyze(latitude,longitude,start_date,end_date,settings,service,runner,include_trend):
    _validate_dates(start_date,end_date,settings); query=PowerPointQuery(latitude,longitude,start_date,end_date,"LST")
    try: result=await runner.run(lambda:service.analyze(query),settings.power_request_timeout_seconds)
    except Exception as exc: _raise_http(exc)
    payload={**_base(query),"variable":"Extreme Heat Frequency","dataset":"NASA POWER","parameter":"T2M_MAX","units":{"temperature":"°C","raw_count":"days","frequency":"%"},"time_standard":"LST","reference_period":{"start_year":1991,"end_year":2020,"complete":result.reference_complete,"valid_days":result.reference_valid_days,"expected_days":result.reference_expected_days},"methodology":{"percentile":90,"window_days":5,"quantile":"Hyndman-Fan type 8","comparison":">","leap_day":"interpolated February 28/March 1 threshold","bootstrap":"Zhang-style leave-one-year-out replacement bootstrap for 1991-2020"},"annual_summaries":[asdict(x) for x in result.annual_summaries],"trend_basis":"bootstrap-adjusted exceedance percentage where applicable","limitations":["Hot-day exceedance frequency is not heatwave frequency or duration.","Values are gridded meteorological estimates, not station observations.","A relative percentile is not an absolute health-risk threshold."]}
    if include_trend: payload["trend"]=asdict(result.trend)
    return payload

@router.get("/extreme-heat",response_model=ExtremeHeatResponse)
async def extreme_heat(latitude:Annotated[float,Query(ge=-90,le=90)],longitude:Annotated[float,Query(ge=-180,le=180)],start_date:date,end_date:date,settings:Settings=Depends(get_settings_dependency),service:ExtremeHeatService=Depends(get_extreme_heat_service),runner:BoundedOperationRunner=Depends(get_power_operation_runner)):
    return await _analyze(latitude,longitude,start_date,end_date,settings,service,runner,False)

@router.get("/extreme-heat/trend",response_model=ExtremeHeatResponse)
async def extreme_heat_trend(latitude:Annotated[float,Query(ge=-90,le=90)],longitude:Annotated[float,Query(ge=-180,le=180)],start_date:date,end_date:date,settings:Settings=Depends(get_settings_dependency),service:ExtremeHeatService=Depends(get_extreme_heat_service),runner:BoundedOperationRunner=Depends(get_power_operation_runner)):
    return await _analyze(latitude,longitude,start_date,end_date,settings,service,runner,True)
