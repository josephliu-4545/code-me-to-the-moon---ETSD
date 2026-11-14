from collections import defaultdict
from statistics import mean, median

from app.statistics.models import AnnualSummary, ObservationSeries
from app.statistics.policies import AnnualAggregationPolicy


def aggregate_annual(
    series: ObservationSeries,
    policy: AnnualAggregationPolicy,
) -> tuple[AnnualSummary, ...]:
    summaries: list[AnnualSummary] = []
    for coverage in sorted(series.coverage_by_year, key=lambda item: item.year):
        source = [item for item in series.observations if item.date.year == coverage.year]
        excluded_for_spatial = False
        if policy.minimum_observation_spatial_coverage is None:
            used = source
        else:
            used = []
            for item in source:
                spatial = item.spatial_coverage_percentage
                if spatial is None or spatial < policy.minimum_observation_spatial_coverage:
                    excluded_for_spatial = True
                else:
                    used.append(item)

        by_month: dict[int, list[float]] = defaultdict(list)
        for item in used:
            by_month[item.date.month].append(item.value)
        monthly = tuple(
            (month, mean(values)) for month, values in sorted(by_month.items())
        )
        represented_months = tuple(month for month, _ in monthly)
        missing_months = tuple(month for month in range(1, 13) if month not in by_month)
        represented_quarters = tuple(
            sorted({((month - 1) // 3) + 1 for month in represented_months})
        )
        missing_quarters = tuple(
            quarter for quarter in range(1, 5) if quarter not in represented_quarters
        )
        expected = len(coverage.expected_slot_dates)
        valid_count = len(source)
        used_count = len(used)
        valid_fraction = valid_count / expected if expected else 0.0
        reasons: list[str] = []
        if policy.exclude_partial_calendar_years_from_inference and not coverage.is_complete_calendar_year:
            reasons.append("partial_calendar_year")
        if not used:
            reasons.append("no_valid_observations")
        if len(represented_months) < policy.minimum_represented_months:
            reasons.append("insufficient_represented_months")
        if valid_fraction < policy.minimum_valid_slot_coverage:
            reasons.append("insufficient_valid_slot_coverage")
        if policy.require_all_quarters and missing_quarters:
            reasons.append("missing_calendar_quarter")
        if excluded_for_spatial:
            reasons.append("low_spatial_coverage_observations_excluded")

        spatial_values = [
            item.spatial_coverage_percentage
            for item in used
            if item.spatial_coverage_percentage is not None
        ]
        summaries.append(
            AnnualSummary(
                year=coverage.year,
                annual_value=mean(value for _, value in monthly) if monthly else None,
                value_units=series.value_units,
                monthly_values=monthly,
                represented_months=represented_months,
                missing_months=missing_months,
                represented_quarters=represented_quarters,
                missing_quarters=missing_quarters,
                valid_observations=valid_count,
                used_observations=used_count,
                expected_observations=expected,
                available_images=len(coverage.available_image_dates),
                valid_coverage_percentage=valid_fraction * 100,
                image_availability_percentage=(
                    len(coverage.available_image_dates) / expected * 100 if expected else 0.0
                ),
                is_complete_calendar_year=coverage.is_complete_calendar_year,
                eligible_for_trend_inference=not reasons,
                eligibility_reasons=tuple(reasons),
                minimum_spatial_coverage_percentage=min(spatial_values) if spatial_values else None,
                mean_spatial_coverage_percentage=mean(spatial_values) if spatial_values else None,
                median_spatial_coverage_percentage=median(spatial_values) if spatial_values else None,
                spatial_coverage_threshold_applied=policy.minimum_observation_spatial_coverage,
            )
        )
    return tuple(summaries)

