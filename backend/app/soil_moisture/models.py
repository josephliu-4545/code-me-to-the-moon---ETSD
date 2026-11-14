"""Monthly soil moisture records, support policy, and reason codes.

These models sit *before* the shared statistical engine. They decide whether a
single dataset's month has enough support to be used; the engine (unchanged)
decides annual eligibility and trends from the months marked usable.

Support thresholds are provisional project policy pending live validation
(decisions D2 and D5). They are not universal scientific standards.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import math
from typing import ClassVar, Mapping

from app.soil_moisture.datasets import DatasetDescriptor, DepthSemantics, ProductType
from app.soil_moisture.units import QuantityKind
from app.statistics.models import AnnualSummary, TrendAnalysisResult


class MonthStatus(StrEnum):
    VALID = "valid"
    INSUFFICIENT_SUPPORT = "insufficient_support"
    INSUFFICIENT_TEMPORAL_SPREAD = "insufficient_temporal_spread"
    NO_IMAGES = "no_images"
    NO_VALID_VALUES = "no_valid_values"
    OUTSIDE_AVAILABILITY = "outside_availability"


class MonthFlag(StrEnum):
    # Within the configured window before the catalog's latest image; may be revised.
    # Deliberately says nothing about which product stream the image came from.
    PROVISIONAL_RECENT_PRODUCT = "provisional_recent_product"
    # Valid month whose slot coverage is below 100%.
    PARTIAL_TEMPORAL_SUPPORT = "partial_temporal_support"
    # Month straddles the start or end of the collection's catalog availability.
    PARTIAL_CATALOG_MONTH = "partial_catalog_month"


# Slots missing at the very start of a record (GLDAS-2.1 starts 2000-01-01T03Z).
_RECORD_START_MISSING_SLOTS: Mapping[str, int] = {"gldas_2_1_noah_0_10cm": 1}


def days_in_month(month: date) -> int:
    return calendar.monthrange(month.year, month.month)[1]


def expected_slots(descriptor: DatasetDescriptor, month: date) -> int:
    """Calendar-derived expected time steps, never inferred from the catalog."""
    if month.day != 1:
        raise ValueError("month must be the first calendar day")
    slots = days_in_month(month) * descriptor.expected_slots_per_day
    if month == descriptor.documented_first_date.replace(day=1):
        slots -= _RECORD_START_MISSING_SLOTS.get(descriptor.key, 0)
    return slots


@dataclass(frozen=True)
class SupportPolicy:
    gldas_min_slot_coverage: float = 0.90
    gldas_provisional_recent_months: int = 4
    smap_min_valid_days: int = 8
    smap_min_valid_days_per_third: int = 1

    is_universal_standard: ClassVar[bool] = False
    status: ClassVar[str] = "provisional_pending_live_validation"

    def __post_init__(self) -> None:
        if not 0 < self.gldas_min_slot_coverage <= 1:
            raise ValueError("GLDAS minimum slot coverage must be in (0, 1]")
        if self.gldas_provisional_recent_months < 0:
            raise ValueError("GLDAS provisional window must not be negative")
        if not 1 <= self.smap_min_valid_days <= 31:
            raise ValueError("SMAP minimum valid days must be between 1 and 31")
        if not 0 <= self.smap_min_valid_days_per_third <= 10:
            raise ValueError("SMAP minimum valid days per third must be between 0 and 10")


@dataclass(frozen=True)
class CatalogAvailability:
    """Live catalog extent for one collection (read at runtime by providers)."""

    collection_id: str
    first_image_date: date
    last_image_date: date

    def __post_init__(self) -> None:
        if not self.collection_id.strip():
            raise ValueError("collection id must be non-empty")
        if self.last_image_date < self.first_image_date:
            raise ValueError("catalog availability ends before it starts")


@dataclass(frozen=True)
class MonthlySample:
    """What a provider reports for one month at the sampled native grid cell.

    ``valid_values`` counts finite, unmasked, QC-pass, in-range values at the cell.
    ``valid_dates`` is required for daily satellite products (one entry per valid day).
    """

    month: date
    available_images: int
    valid_values: int
    mean_native: float | None
    valid_dates: tuple[date, ...] | None = None
    # Images whose catalog product status is not "permanent" (GLDAS marks Early-stream
    # images "early"). None = status unknown, so the time-window fallback applies.
    nonpermanent_images: int | None = None

    def __post_init__(self) -> None:
        if self.month.day != 1:
            raise ValueError("month must be the first calendar day")
        if self.available_images < 0 or self.valid_values < 0:
            raise ValueError("counts must not be negative")
        if self.nonpermanent_images is not None and not (
            0 <= self.nonpermanent_images <= self.available_images
        ):
            raise ValueError("nonpermanent images must be between 0 and available images")
        if self.valid_values > self.available_images:
            raise ValueError("valid values cannot exceed available images")
        if (self.mean_native is None) != (self.valid_values == 0):
            raise ValueError("mean must be present exactly when valid values exist")
        if self.mean_native is not None and not math.isfinite(self.mean_native):
            raise ValueError("mean must be finite")
        if self.valid_dates is not None:
            if len(set(self.valid_dates)) != len(self.valid_dates):
                raise ValueError("valid dates must be unique")
            if any((d.year, d.month) != (self.month.year, self.month.month) for d in self.valid_dates):
                raise ValueError("valid dates must fall within the month")
            if len(self.valid_dates) != self.valid_values:
                raise ValueError("number of valid dates must equal valid_values")


@dataclass(frozen=True)
class MonthlySoilMoisture:
    dataset_key: str
    collection_id: str
    version: str
    month: date
    status: MonthStatus
    flags: tuple[MonthFlag, ...]
    expected_slots: int
    available_images: int
    valid_values: int
    mean_native: float | None             # only for VALID months; never 0 for missing
    descriptive_mean_native: float | None  # sampled mean, shown even when withheld
    derived_volumetric: float | None       # GLDAS layer mean in m3 m-3; None otherwise
    units: str
    derived_units: str | None
    value_definition: str
    valid_days_by_third: tuple[int, int, int] | None = None
    missing_thirds: tuple[int, ...] = ()
    longest_gap_days: int | None = None

    def __post_init__(self) -> None:
        if self.month.day != 1:
            raise ValueError("month must be the first calendar day")
        if (self.descriptive_mean_native is None) != (self.valid_values == 0):
            raise ValueError("a descriptive mean exists exactly when valid values exist")
        if (self.mean_native is not None) != (self.status is MonthStatus.VALID and
                                             self.descriptive_mean_native is not None):
            raise ValueError("a mean is published only for valid months")
        if self.derived_volumetric is not None and self.derived_units is None:
            raise ValueError("derived value requires derived units")

    @property
    def slot_coverage(self) -> float:
        return self.valid_values / self.expected_slots if self.expected_slots else 0.0

    @property
    def inference_exclusion_reasons(self) -> tuple[str, ...]:
        reasons = [] if self.status is MonthStatus.VALID else [self.status.value]
        if MonthFlag.PROVISIONAL_RECENT_PRODUCT in self.flags:
            reasons.append(MonthFlag.PROVISIONAL_RECENT_PRODUCT.value)
        return tuple(reasons)

    @property
    def usable_for_inference(self) -> bool:
        return not self.inference_exclusion_reasons


@dataclass(frozen=True)
class MonthlySoilMoistureSeries:
    dataset_key: str
    months: tuple[MonthlySoilMoisture, ...]

    def __post_init__(self) -> None:
        if any(r.dataset_key != self.dataset_key for r in self.months):
            raise ValueError("a series must contain a single dataset")
        keys = [r.month for r in self.months]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate months in series")
        if keys != sorted(keys):
            raise ValueError("months must be in chronological order")


@dataclass(frozen=True)
class YearSupport:
    """Descriptive monthly support for one calendar year (not an eligibility verdict)."""

    year: int
    is_complete_calendar_year: bool
    requested_months: int
    usable_months: int
    missing_months: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class SoilMoistureAnalysis:
    """One dataset's monthly support, annual summaries, and trend (never merged).

    ``annual_summaries`` and ``trend`` come unchanged from the shared engine in the
    dataset's native units. GLDAS also gets a derived 0-10 cm layer-mean m3 m-3 run;
    it is not equivalent to SMAP's ~0-5 cm retrieval.
    """

    dataset_key: str
    collection_id: str
    version: str
    product_type: ProductType
    quantity_kind: QuantityKind
    units: str
    depth_top_cm: float
    depth_bottom_cm: float
    depth_semantics: DepthSemantics
    value_definition: str
    annual_aggregation: str
    monthly: MonthlySoilMoistureSeries
    year_support: tuple[YearSupport, ...]
    annual_summaries: tuple[AnnualSummary, ...]
    trend: TrendAnalysisResult
    derived_units: str | None
    derived_annual_summaries: tuple[AnnualSummary, ...] | None
    derived_trend: TrendAnalysisResult | None
    support_policy_status: str
    thresholds_are_universal_standards: bool
