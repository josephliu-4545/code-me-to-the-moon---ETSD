from dataclasses import dataclass
from datetime import date
import math


@dataclass(frozen=True)
class TimedValue:
    date: date
    value: float
    spatial_coverage_percentage: float | None = None
    valid_pixel_count: int | None = None
    total_pixel_count: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("value must be finite")
        if self.spatial_coverage_percentage is not None and not (
            0 <= self.spatial_coverage_percentage <= 100
        ):
            raise ValueError("spatial coverage must be between 0 and 100")
        if (self.valid_pixel_count is None) != (self.total_pixel_count is None):
            raise ValueError("pixel counts must be provided together")
        if self.valid_pixel_count is not None:
            if self.valid_pixel_count < 0 or self.total_pixel_count <= 0:
                raise ValueError("pixel counts are invalid")
            if self.valid_pixel_count > self.total_pixel_count:
                raise ValueError("valid pixels cannot exceed total pixels")


@dataclass(frozen=True)
class YearCoverage:
    year: int
    expected_slot_dates: tuple[date, ...]
    available_image_dates: tuple[date, ...]
    is_complete_calendar_year: bool

    def __post_init__(self) -> None:
        if len(set(self.expected_slot_dates)) != len(self.expected_slot_dates):
            raise ValueError("expected slot dates must be unique")
        if len(set(self.available_image_dates)) != len(self.available_image_dates):
            raise ValueError("available image dates must be unique")
        if any(day.year != self.year for day in self.expected_slot_dates):
            raise ValueError("expected slot date is outside coverage year")
        if not set(self.available_image_dates).issubset(self.expected_slot_dates):
            raise ValueError("available image dates must be expected slots")


@dataclass(frozen=True)
class ObservationSeries:
    variable: str
    value_units: str
    dataset: str
    observations: tuple[TimedValue, ...]
    coverage_by_year: tuple[YearCoverage, ...]

    def __post_init__(self) -> None:
        dates = [item.date for item in self.observations]
        if len(set(dates)) != len(dates):
            raise ValueError("observation dates must be unique")
        available = {
            day for coverage in self.coverage_by_year for day in coverage.available_image_dates
        }
        if not set(dates).issubset(available):
            raise ValueError("valid observations require available catalog images")


@dataclass(frozen=True)
class AnnualSummary:
    year: int
    annual_value: float | None
    value_units: str
    monthly_values: tuple[tuple[int, float], ...]
    represented_months: tuple[int, ...]
    missing_months: tuple[int, ...]
    represented_quarters: tuple[int, ...]
    missing_quarters: tuple[int, ...]
    valid_observations: int
    used_observations: int
    expected_observations: int
    available_images: int
    valid_coverage_percentage: float
    image_availability_percentage: float
    is_complete_calendar_year: bool
    eligible_for_trend_inference: bool
    eligibility_reasons: tuple[str, ...]
    minimum_spatial_coverage_percentage: float | None
    mean_spatial_coverage_percentage: float | None
    median_spatial_coverage_percentage: float | None
    spatial_coverage_threshold_applied: float | None


@dataclass(frozen=True)
class TheilSenResult:
    slope: float
    intercept: float
    slope_units: str
    confidence_interval: tuple[float, float] | None
    confidence_interval_unavailable_reason: str | None


@dataclass(frozen=True)
class SerialDependenceResult:
    adjacent_pair_count: int
    lag1_spearman_rho: float | None
    diagnostic_p_value: float | None
    status: str
    caveat: str
    supported_for_standard_inference: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class MannKendallResult:
    s: int
    variance: float
    z: float
    tau: float
    p_value: float
    alpha: float
    alternative: str
    is_statistically_significant: bool
    direction: str


@dataclass(frozen=True)
class TrendAnalysisResult:
    result_level: str
    eligible_years: tuple[int, ...]
    excluded_years: tuple[tuple[int, tuple[str, ...]], ...]
    missing_years: tuple[int, ...]
    theil_sen: TheilSenResult | None
    serial_dependence: SerialDependenceResult | None
    mann_kendall: MannKendallResult | None
    slope_unavailable_reason: str | None
    significance_unavailable_reason: str | None

