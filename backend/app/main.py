from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.ndvi import router as ndvi_router
from app.api.routes.ndvi_trend import router as ndvi_trend_router
from app.api.routes.relative_humidity import router as relative_humidity_router
from app.api.routes.temperature import router as temperature_router
from app.api.routes.extreme_heat import router as extreme_heat_router
from app.api.routes.precipitation import router as precipitation_router
from app.api.routes.soil_moisture import router as soil_moisture_router
from app.api.routes.precipitation_region import router as precipitation_region_router
from app.services.imerg_region_service import ImergRegionService
from app.api.routes.unified import ResultCache, router as unified_router
from app.api.routes.comparison import router as comparison_router
from app.api.routes.status import router as status_router
from app.core.access import AccessControlMiddleware, TokenBucket, parse_keys
from app.core.ee_credentials import earth_engine_module
from app.core.config import Settings, get_settings
from app.core.earth_engine import EarthEngineError, EarthEngineManager
from app.core.operation_runner import (
    BoundedOperationRunner,
    OperationBusyError,
    OperationTimeoutError,
)
from app.services.modis_service import ModisService
from app.services.ndvi_chunked import YearChunkedNDVIProvider
from app.services.ndvi_trend_service import NDVITrendService
from app.power.client import PowerClient
from app.services.relative_humidity_service import RelativeHumidityPolicy, RelativeHumidityService
from app.services.temperature_service import TemperatureService
from app.extremes.hot_days import HotDayPolicy
from app.services.extreme_heat_service import ExtremeHeatService
from app.services.imerg_service import ImergService
from app.services.precipitation_service import PrecipitationService
from app.precipitation.models import PrecipitationPolicy
from app.services.soil_moisture_provider import EarthEngineSoilMoistureProvider
from app.services.soil_moisture_service import SoilMoistureService
from app.soil_moisture.models import SupportPolicy


def create_app(
    settings: Settings | None = None,
    ee_manager: EarthEngineManager | None = None,
    modis_service: ModisService | None = None,
    operation_runner: BoundedOperationRunner | None = None,
    ndvi_trend_service: NDVITrendService | None = None,
    relative_humidity_service: RelativeHumidityService | None = None,
    power_operation_runner: BoundedOperationRunner | None = None,
    temperature_service: TemperatureService | None = None,
    extreme_heat_service: ExtremeHeatService | None = None,
    precipitation_service: PrecipitationService | None = None,
    soil_moisture_service: SoilMoistureService | None = None,
    imerg_region_service: ImergRegionService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_manager = ee_manager or EarthEngineManager(
        resolved_settings.ee_project_id, earth_engine_module(resolved_settings.ee_service_account_key_file)
    )
    resolved_service = modis_service or ModisService(resolved_manager)
    resolved_runner = operation_runner or BoundedOperationRunner(
        resolved_settings.ee_max_concurrent_operations,
        queue_timeout_seconds=resolved_settings.operation_queue_timeout_seconds,
    )
    resolved_trend_service = ndvi_trend_service or NDVITrendService(
        YearChunkedNDVIProvider(resolved_service), resolved_settings
    )
    resolved_power_service = relative_humidity_service or RelativeHumidityService(
        PowerClient(
            base_url=resolved_settings.power_base_url,
            timeout_seconds=resolved_settings.power_http_timeout_seconds,
            window_years=resolved_settings.power_window_years,
        ),
        RelativeHumidityPolicy(
            minimum_annual_coverage=resolved_settings.rh_min_annual_coverage,
            minimum_monthly_coverage=resolved_settings.rh_min_monthly_coverage,
        ),
    )
    resolved_power_runner = power_operation_runner or BoundedOperationRunner(
        resolved_settings.power_max_concurrent_operations,
        operation_name="NASA POWER",
        thread_name_prefix="nasa-power",
        queue_timeout_seconds=resolved_settings.operation_queue_timeout_seconds,
    )
    resolved_temperature_service = temperature_service or TemperatureService(PowerClient(base_url=resolved_settings.power_base_url,timeout_seconds=resolved_settings.power_http_timeout_seconds,window_years=resolved_settings.power_window_years))
    resolved_extreme_heat_service = extreme_heat_service or ExtremeHeatService(
        PowerClient(base_url=resolved_settings.power_base_url,timeout_seconds=resolved_settings.power_http_timeout_seconds,window_years=resolved_settings.power_window_years),
        HotDayPolicy(reference_start_year=resolved_settings.heat_reference_start_year,reference_end_year=resolved_settings.heat_reference_end_year,minimum_window_fraction=resolved_settings.heat_reference_minimum_window_fraction,maximum_missing_days_per_year=resolved_settings.heat_maximum_missing_days_per_year,maximum_missing_days_per_month=resolved_settings.heat_maximum_missing_days_per_month),
        cache_max_entries=resolved_settings.heat_reference_cache_max_entries,
    )
    resolved_precipitation_service = precipitation_service or PrecipitationService(
        ImergService(
            resolved_manager,
            window_years=resolved_settings.precipitation_window_years,
            cache_max_entries=resolved_settings.precipitation_cache_max_entries,
            cache_ttl_seconds=resolved_settings.precipitation_cache_ttl_seconds,
        ),
        PrecipitationPolicy(minimum_valid_months=resolved_settings.precipitation_min_valid_months),
    )
    resolved_soil_moisture_service = soil_moisture_service or SoilMoistureService(
        EarthEngineSoilMoistureProvider(
            resolved_manager,
            window_years=resolved_settings.soil_moisture_window_years,
            smap_window_years=resolved_settings.soil_moisture_smap_window_years,
            max_parallel_windows=resolved_settings.soil_moisture_max_parallel_windows,
            cache_max_entries=resolved_settings.soil_moisture_cache_max_entries,
            cache_ttl_seconds=resolved_settings.soil_moisture_cache_ttl_seconds,
        ),
        SupportPolicy(
            gldas_min_slot_coverage=resolved_settings.soil_moisture_gldas_min_month_slot_coverage,
            gldas_provisional_recent_months=resolved_settings.soil_moisture_gldas_exclude_recent_months,
            smap_min_valid_days=resolved_settings.soil_moisture_smap_min_valid_days_per_month,
            smap_min_valid_days_per_third=resolved_settings.soil_moisture_smap_min_valid_days_per_third,
        ),
        compare_min_overlap_months=resolved_settings.soil_moisture_compare_min_overlap_months,
    )
    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
    )

    @application.get("/")
    async def homepage() -> dict[str, str]:
        return {
            "name": resolved_settings.app_name,
            "version": resolved_settings.app_version,
            "status": "ok",
        }

    @application.get("/health")
    async def health() -> JSONResponse:
        try:
            await resolved_runner.run(
                resolved_manager.initialize,
                timeout_seconds=resolved_settings.ee_request_timeout_seconds,
            )
        except (EarthEngineError, OperationBusyError, OperationTimeoutError):
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "earth_engine": "failed"},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "earth_engine": "ready"},
        )

    application.state.settings = resolved_settings
    application.state.ee_manager = resolved_manager
    application.state.modis_service = resolved_service
    application.state.operation_runner = resolved_runner
    application.state.ndvi_trend_service = resolved_trend_service
    application.state.relative_humidity_service = resolved_power_service
    application.state.power_operation_runner = resolved_power_runner
    application.state.temperature_service = resolved_temperature_service
    application.state.extreme_heat_service = resolved_extreme_heat_service
    application.state.precipitation_service = resolved_precipitation_service
    application.state.soil_moisture_service = resolved_soil_moisture_service
    application.state.imerg_region_service = imerg_region_service or ImergRegionService(
        resolved_manager,
        window_years=resolved_settings.precipitation_window_years,
        min_valid_area_fraction=resolved_settings.precipitation_region_min_valid_area_fraction,
        cache_max_entries=resolved_settings.precipitation_cache_max_entries,
        cache_ttl_seconds=resolved_settings.precipitation_cache_ttl_seconds,
    )
    application.include_router(ndvi_router)
    application.include_router(ndvi_trend_router)
    application.include_router(relative_humidity_router)
    application.include_router(temperature_router)
    application.include_router(extreme_heat_router)
    application.include_router(precipitation_router)
    application.include_router(soil_moisture_router)
    application.include_router(precipitation_region_router)
    application.include_router(unified_router)
    application.include_router(comparison_router)
    application.include_router(status_router)
    keys = parse_keys(resolved_settings.api_keys)
    if keys or resolved_settings.rate_limit_per_minute:
        application.add_middleware(
            AccessControlMiddleware,
            api_keys=keys,
            bucket=TokenBucket(resolved_settings.rate_limit_per_minute) if resolved_settings.rate_limit_per_minute else None,
            trust_proxy_headers=resolved_settings.trust_proxy_headers,
        )
    application.state.unified_cache = ResultCache(
        resolved_settings.unified_cache_max_entries, resolved_settings.unified_cache_ttl_seconds
    )
    if resolved_settings.frontend_dist_dir:
        from pathlib import Path

        from fastapi.staticfiles import StaticFiles

        dist = Path(resolved_settings.frontend_dist_dir)
        if (dist / "index.html").is_file():
            application.mount("/app", StaticFiles(directory=dist, html=True), name="frontend")
    origins = [o.strip() for o in resolved_settings.cors_allow_origins.split(",") if o.strip()]
    if origins:
        application.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"]
        )

    return application


app = create_app()

