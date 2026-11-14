import calendar
from datetime import date, timedelta
import math

from app.precipitation.models import (
    AnnualPrecipitationSummary,
    MonthlyPrecipitationSeries,
    PrecipitationPolicy,
    PrecipitationQuery,
)


def monthly_rate_to_accumulation(rate_mm_per_hour: float, year: int, month: int) -> float:
    if not math.isfinite(rate_mm_per_hour) or rate_mm_per_hour < 0:
        raise ValueError("rate must be finite and nonnegative")
    days = calendar.monthrange(year, month)[1]
    return rate_mm_per_hour * 24 * days


def aggregate_precipitation_years(
    series: MonthlyPrecipitationSeries,
    query: PrecipitationQuery,
    policy: PrecipitationPolicy,
) -> tuple[AnnualPrecipitationSummary, ...]:
    last = query.end_date - timedelta(days=1)
    by_key = {
        (item.month.year, item.month.month): item
        for item in series.observations
        if query.start_date <= item.month < query.end_date
    }
    results: list[AnnualPrecipitationSummary] = []
    for year in range(query.start_date.year, last.year + 1):
        complete = query.start_date <= date(year, 1, 1) and query.end_date >= date(year + 1, 1, 1)
        catalog = [by_key.get((year, month)) for month in range(1, 13)]
        available = [item for item in catalog if item is not None and item.catalog_available]
        valid = [item for item in available if item.accumulation_mm is not None]
        represented = tuple(item.month.month for item in valid)
        missing = tuple(month for month in range(1, 13) if month not in represented)
        reasons: list[str] = []
        if policy.require_complete_calendar_year and not complete:
            reasons.append("partial_calendar_year")
        if len(available) < 12:
            reasons.append("missing_catalog_month")
        if len(available) == 12 and len(valid) < 12:
            reasons.append("missing_monthly_value")
        # A precipitation annual total is defined only from all 12 months.
        # The configurable policy may be made stricter in future, never looser.
        if len(valid) < max(12, policy.minimum_valid_months):
            reasons.append("insufficient_valid_months")
        mixed = any(
            item.dataset_id != "NASA/GPM_L3/IMERG_MONTHLY_V07"
            or item.version != "07"
            or item.run != "Final"
            or item.status != "permanent"
            for item in available
        )
        if mixed:
            reasons.append("mixed_or_nonfinal_product")
        monthly = tuple((item.month.month, float(item.accumulation_mm)) for item in valid)
        observed = sum(value for _, value in monthly)
        eligible = not reasons
        results.append(AnnualPrecipitationSummary(
            year=year,
            annual_accumulation_mm=observed if len(valid) == 12 and complete else None,
            observed_accumulation_mm=observed,
            represented_months=represented,
            missing_months=missing,
            catalog_months=len(available),
            valid_months=len(valid),
            expected_months=12,
            catalog_coverage_percentage=len(available) / 12 * 100,
            valid_coverage_percentage=len(valid) / 12 * 100,
            is_complete_calendar_year=complete,
            eligible_for_trend_inference=eligible,
            eligibility_reasons=tuple(reasons),
            monthly_accumulations=monthly,
        ))
    return tuple(results)

