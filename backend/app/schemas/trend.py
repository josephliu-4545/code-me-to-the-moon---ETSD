from datetime import date
from typing import Any

from pydantic import BaseModel

from app.schemas.ndvi import NDVILocation, NDVIPeriod


class AnnualSummaryResponse(BaseModel):
    year: int
    annual_value: float | None
    value_units: str
    monthly_values: dict[int, float]
    represented_months: list[int]
    missing_months: list[int]
    represented_quarters: list[int]
    missing_quarters: list[int]
    valid_observations: int
    used_observations: int
    expected_observations: int
    available_images: int
    valid_coverage_percentage: float
    image_availability_percentage: float
    is_complete_calendar_year: bool
    eligible_for_trend_inference: bool
    eligibility_reasons: list[str]
    minimum_spatial_coverage_percentage: float | None
    mean_spatial_coverage_percentage: float | None
    median_spatial_coverage_percentage: float | None
    spatial_coverage_threshold_applied: float | None


class TheilSenResponse(BaseModel):
    slope: float
    intercept: float
    slope_units: str
    confidence_interval: list[float] | None
    confidence_interval_unavailable_reason: str | None


class SerialDependenceResponse(BaseModel):
    adjacent_pair_count: int
    lag1_spearman_rho: float | None
    diagnostic_p_value: float | None
    status: str
    caveat: str
    supported_for_standard_inference: bool
    unavailable_reason: str | None


class MannKendallResponse(BaseModel):
    s: int
    variance: float
    z: float
    tau: float
    p_value: float
    alpha: float
    alternative: str
    is_statistically_significant: bool
    direction: str


class TrendResultResponse(BaseModel):
    result_level: str
    eligible_years: list[int]
    excluded_years: list[dict[str, Any]]
    missing_years: list[int]
    theil_sen: TheilSenResponse | None
    serial_dependence: SerialDependenceResponse | None
    mann_kendall: MannKendallResponse | None
    slope_unavailable_reason: str | None
    significance_unavailable_reason: str | None


class NDVITrendResponse(BaseModel):
    variable: str
    dataset: str
    units: str
    location: NDVILocation
    period: NDVIPeriod
    observation_count: int
    eligible_annual_observation_count: int
    annual_summaries: list[AnnualSummaryResponse]
    trend: TrendResultResponse
    coverage_definitions: dict[str, str]
    methodology: dict[str, Any]
    limitations: list[str]

