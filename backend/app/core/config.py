from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NASA Earth System Trend Detective API"
    app_version: str = "0.1.0"
    ee_project_id: str | None = None
    # Shared deployments: path to a service-account JSON key kept OUTSIDE the repository.
    ee_service_account_key_file: str | None = None
    # Keyless alternative (recommended on Cloud Run): use Application Default Credentials, e.g. the
    # service account attached to the service. Mutually exclusive with EE_SERVICE_ACCOUNT_KEY_FILE.
    ee_use_application_default_credentials: bool = False
    ee_max_concurrent_operations: int = Field(default=2, ge=1, le=16)
    ee_request_timeout_seconds: float = Field(default=60.0, gt=0)
    # Seconds a request waits for a free Earth Engine / NASA POWER slot before 503 "busy".
    operation_queue_timeout_seconds: float = Field(default=20.0, ge=0)
    ndvi_max_radius_km: float = Field(default=100.0, gt=0)
    ndvi_max_date_range_years: int = Field(default=10, ge=1)
    # Trend requests are fetched one calendar year at a time, so they can span the whole MODIS record.
    ndvi_trend_max_date_range_years: int = Field(default=30, ge=1)
    annual_min_represented_months: int = Field(default=9, ge=1, le=12)
    annual_min_valid_coverage: float = Field(default=0.70, ge=0, le=1)
    annual_require_all_quarters: bool = True
    annual_exclude_partial_years: bool = True
    annual_min_observation_spatial_coverage: float | None = Field(
        default=None, ge=0, le=100
    )
    trend_min_slope_years: int = Field(default=3, ge=3)
    trend_min_significance_years: int = Field(default=8, ge=3)
    trend_significance_alpha: float = Field(default=0.05, gt=0, lt=1)
    trend_min_adjacent_pairs: int = Field(default=6, ge=2)
    trend_material_lag1_rho: float = Field(default=0.30, ge=0, le=1)
    power_base_url: str = "https://power.larc.nasa.gov/api/temporal"
    power_http_timeout_seconds: float = Field(default=30.0, gt=0)
    power_request_timeout_seconds: float = Field(default=60.0, gt=0)
    power_max_concurrent_operations: int = Field(default=2, ge=1, le=16)
    power_max_date_range_years: int = Field(default=50, ge=1)
    # Calendar years per daily NASA POWER request. 10 returned identical daily values
    # to 1-year windows in live checks; set POWER_WINDOW_YEARS=1 to roll back.
    power_window_years: int = Field(default=10, ge=1, le=10)
    rh_min_annual_coverage: float = Field(default=0.90, ge=0, le=1)
    rh_min_monthly_coverage: float = Field(default=0.80, ge=0, le=1)
    heat_reference_start_year: int = 1991
    heat_reference_end_year: int = 2020
    heat_reference_minimum_window_fraction: float = Field(default=0.75, gt=0, le=1)
    heat_maximum_missing_days_per_year: int = Field(default=15, ge=0)
    heat_maximum_missing_days_per_month: int = Field(default=3, ge=0)
    heat_reference_cache_max_entries: int = Field(default=16, ge=1, le=256)
    # Point and region requests are fetched in precipitation_window_years windows; 25 years took 6-13 s live.
    precipitation_max_date_range_years: int = Field(default=30, ge=1)
    precipitation_window_years: int = Field(default=5, ge=1, le=10)
    precipitation_min_valid_months: int = Field(default=12, ge=1, le=12)
    precipitation_cache_max_entries: int = Field(default=32, ge=1, le=256)
    precipitation_cache_ttl_seconds: float = Field(default=3600, gt=0)
    precipitation_region_max_span_degrees: float = Field(default=5.0, gt=0, le=20)
    precipitation_region_min_valid_area_fraction: float = Field(default=0.95, gt=0, le=1)
    soil_moisture_max_date_range_years: int = Field(default=27, ge=1)
    soil_moisture_window_years: int = Field(default=5, ge=1, le=10)
    soil_moisture_smap_window_years: int = Field(default=2, ge=1, le=10)
    soil_moisture_max_parallel_windows: int = Field(default=5, ge=1, le=8)
    soil_moisture_request_timeout_seconds: float = Field(default=180.0, gt=0)
    soil_moisture_gldas_min_month_slot_coverage: float = Field(default=0.90, gt=0, le=1)
    soil_moisture_gldas_exclude_recent_months: int = Field(default=4, ge=0)
    soil_moisture_smap_min_valid_days_per_month: int = Field(default=8, ge=1, le=31)
    soil_moisture_smap_min_valid_days_per_third: int = Field(default=1, ge=0, le=10)
    soil_moisture_compare_min_overlap_months: int = Field(default=36, ge=1)
    soil_moisture_cache_max_entries: int = Field(default=32, ge=1, le=256)
    soil_moisture_cache_ttl_seconds: float = Field(default=3600, gt=0)
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional path to the built frontend (frontend/dist); when set it is served at /app/.
    frontend_dist_dir: str | None = None
    # Shared deployments: comma-separated team access keys (X-API-Key) and per-client rate limit.
    api_keys: str | None = None
    rate_limit_per_minute: int = Field(default=0, ge=0, le=10000)
    # Forwarding headers are client-controlled. They are used only when TRUST_PROXY_HEADERS is on AND the
    # direct peer is in TRUSTED_PROXY_IPS (comma-separated IPs/CIDRs, or "*" only on platforms whose
    # ingress always passes through their own proxy). TRUSTED_PROXY_HOPS = trusted proxies that append.
    trust_proxy_headers: bool = False
    trusted_proxy_ips: str | None = None
    trusted_proxy_hops: int = Field(default=1, ge=0, le=10)
    unified_cache_max_entries: int = Field(default=128, ge=1, le=2048)
    unified_cache_ttl_seconds: float = Field(default=3600, gt=0)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=90.0, gt=0, le=180)


@lru_cache
def get_settings() -> Settings:
    return Settings()

