from fastapi import Request

from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner
from app.services.modis_service import ModisService
from app.services.ndvi_trend_service import NDVITrendService
from app.services.relative_humidity_service import RelativeHumidityService
from app.services.temperature_service import TemperatureService
from app.services.extreme_heat_service import ExtremeHeatService
from app.services.precipitation_service import PrecipitationService


def get_settings_dependency(request: Request) -> Settings:
    return request.app.state.settings


def get_modis_service(request: Request) -> ModisService:
    return request.app.state.modis_service


def get_operation_runner(request: Request) -> BoundedOperationRunner:
    return request.app.state.operation_runner


def get_ndvi_trend_service(request: Request) -> NDVITrendService:
    return request.app.state.ndvi_trend_service


def get_relative_humidity_service(request: Request) -> RelativeHumidityService:
    return request.app.state.relative_humidity_service


def get_power_operation_runner(request: Request) -> BoundedOperationRunner:
    return request.app.state.power_operation_runner

def get_temperature_service(request: Request) -> TemperatureService:
    return request.app.state.temperature_service

def get_extreme_heat_service(request: Request) -> ExtremeHeatService:
    return request.app.state.extreme_heat_service

def get_precipitation_service(request: Request) -> PrecipitationService:
    return request.app.state.precipitation_service

