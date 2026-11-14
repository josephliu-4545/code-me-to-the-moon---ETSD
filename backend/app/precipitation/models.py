from dataclasses import dataclass
from datetime import date
import math


DATASET_ID = "NASA/GPM_L3/IMERG_MONTHLY_V07"
DATASET_VERSION = "07"
PRODUCT_RUN = "Final"
PRODUCT_STATUS = "permanent"


@dataclass(frozen=True)
class PrecipitationQuery:
    latitude: float
    longitude: float
    start_date: date
    end_date: date
    support_type: str = "native_grid_cell"

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if self.end_date <= self.start_date:
            raise ValueError("end date must be after start date")
        if self.support_type != "native_grid_cell":
            raise ValueError("only native_grid_cell support is available")


@dataclass(frozen=True)
class PrecipitationPolicy:
    minimum_valid_months: int = 12
    require_complete_calendar_year: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_valid_months <= 12:
            raise ValueError("minimum valid months must be between 1 and 12")


@dataclass(frozen=True)
class MonthlyPrecipitation:
    month: date
    mean_rate_mm_per_hour: float | None
    accumulation_mm: float | None
    catalog_available: bool
    dataset_id: str = DATASET_ID
    version: str = DATASET_VERSION
    run: str = PRODUCT_RUN
    status: str = PRODUCT_STATUS

    def __post_init__(self) -> None:
        if self.month.day != 1:
            raise ValueError("month must be the first calendar day")
        for value in (self.mean_rate_mm_per_hour, self.accumulation_mm):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("precipitation values must be finite and nonnegative")
        if (self.mean_rate_mm_per_hour is None) != (self.accumulation_mm is None):
            raise ValueError("rate and accumulation must be present together")


@dataclass(frozen=True)
class MonthlyPrecipitationSeries:
    observations: tuple[MonthlyPrecipitation, ...]
    grid_cell_id: str
    grid_cell_center: tuple[float, float] | None = None
    projection: str = "EPSG:4326"
    grid_spacing_degrees: float = 0.1
    nominal_pixel_size_metres: int = 11132

    def __post_init__(self) -> None:
        keys = [(item.month.year, item.month.month) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("monthly observations must be unique")


@dataclass(frozen=True)
class AnnualPrecipitationSummary:
    year: int
    annual_accumulation_mm: float | None
    observed_accumulation_mm: float
    represented_months: tuple[int, ...]
    missing_months: tuple[int, ...]
    catalog_months: int
    valid_months: int
    expected_months: int
    catalog_coverage_percentage: float
    valid_coverage_percentage: float
    is_complete_calendar_year: bool
    eligible_for_trend_inference: bool
    eligibility_reasons: tuple[str, ...]
    monthly_accumulations: tuple[tuple[int, float], ...]

