from dataclasses import asdict
from typing import Protocol

from app.core.config import Settings
from app.schemas.ndvi import NDVILocation, NDVIPeriod, NDVIQuery
from app.schemas.trend import NDVITrendResponse
from app.statistics.annual import aggregate_annual
from app.statistics.models import ObservationSeries
from app.statistics.policies import AnnualAggregationPolicy, TrendPolicy
from app.statistics.trend import analyze_trend


class NDVISeriesProvider(Protocol):
    def fetch_ndvi_series(self, query: NDVIQuery) -> ObservationSeries: ...


class NDVITrendService:
    def __init__(self, provider: NDVISeriesProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    def analyze(self, query: NDVIQuery) -> NDVITrendResponse:
        series = self._provider.fetch_ndvi_series(query)
        annual_policy = AnnualAggregationPolicy(
            minimum_represented_months=self._settings.annual_min_represented_months,
            minimum_valid_slot_coverage=self._settings.annual_min_valid_coverage,
            require_all_quarters=self._settings.annual_require_all_quarters,
            exclude_partial_calendar_years_from_inference=(
                self._settings.annual_exclude_partial_years
            ),
            minimum_observation_spatial_coverage=(
                self._settings.annual_min_observation_spatial_coverage
            ),
        )
        trend_policy = TrendPolicy(
            minimum_slope_years=self._settings.trend_min_slope_years,
            minimum_significance_years=self._settings.trend_min_significance_years,
            alpha=self._settings.trend_significance_alpha,
            minimum_adjacent_residual_pairs=self._settings.trend_min_adjacent_pairs,
            material_lag1_rho=self._settings.trend_material_lag1_rho,
        )
        summaries = aggregate_annual(series, annual_policy)
        trend = analyze_trend(summaries, series.value_units, trend_policy)
        summary_payloads = []
        for summary in summaries:
            payload = asdict(summary)
            payload["monthly_values"] = dict(summary.monthly_values)
            summary_payloads.append(payload)
        trend_payload = asdict(trend)
        trend_payload["excluded_years"] = [
            {"year": year, "reasons": list(reasons)}
            for year, reasons in trend.excluded_years
        ]
        return NDVITrendResponse.model_validate(
            {
                "variable": series.variable,
                "dataset": series.dataset,
                "units": series.value_units,
                "location": NDVILocation(
                    latitude=query.latitude,
                    longitude=query.longitude,
                    radius_km=query.radius_km,
                ),
                "period": NDVIPeriod(start=query.start_date, end=query.end_date),
                "observation_count": len(series.observations),
                "eligible_annual_observation_count": len(trend.eligible_years),
                "annual_summaries": summary_payloads,
                "trend": trend_payload,
                "coverage_definitions": {
                    "expected_observations": "Nominal full-calendar-year dataset composite slots.",
                    "available_images": "Catalog images present before regional quality filtering.",
                    "valid_observations": "Images producing a finite quality-filtered regional value.",
                    "spatial_coverage": "Percent of regional pixels contributing to each valid mean.",
                },
                "methodology": {
                    "annual_aggregation": "Equal-weight mean of represented monthly means.",
                    "minimum_represented_months": annual_policy.minimum_represented_months,
                    "minimum_valid_slot_coverage": annual_policy.minimum_valid_slot_coverage,
                    "require_all_quarters": annual_policy.require_all_quarters,
                    "exclude_partial_years": annual_policy.exclude_partial_calendar_years_from_inference,
                    "minimum_observation_spatial_coverage": annual_policy.minimum_observation_spatial_coverage,
                    "minimum_slope_years": trend_policy.minimum_slope_years,
                    "minimum_significance_years": trend_policy.minimum_significance_years,
                    "significance_alpha": trend_policy.alpha,
                    "thresholds_are_universal_standards": False,
                },
                "limitations": [
                    "Coverage thresholds are configurable policy choices, not universal scientific standards.",
                    "Monthly stratification reduces but does not eliminate seasonal sampling bias.",
                    "Quality filtering can create nonrandom missingness.",
                    "A nonsignificant autocorrelation diagnostic does not prove independence.",
                    "Statistical association does not establish causation or attribution.",
                ] + (
                    ["No minimum spatial-coverage eligibility threshold was applied; spatial support is reported descriptively."]
                    if annual_policy.minimum_observation_spatial_coverage is None
                    else []
                ),
            }
        )

