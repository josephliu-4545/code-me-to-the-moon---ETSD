from dataclasses import dataclass, replace
from statistics import median

from app.precipitation.aggregation import aggregate_precipitation_years
from app.precipitation.models import AnnualPrecipitationSummary, MonthlyPrecipitationSeries, PrecipitationPolicy, PrecipitationQuery
from app.statistics.models import AnnualSummary, TrendAnalysisResult
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


@dataclass(frozen=True)
class PrecipitationAnalysis:
    series: MonthlyPrecipitationSeries
    annual_summaries: tuple[AnnualPrecipitationSummary, ...]
    trend: TrendAnalysisResult
    annual_total_change_mm_per_calendar_year: float | None
    relative_change_percent_per_year: float | None = None
    relative_reference_median_mm: float | None = None


class PrecipitationService:
    def __init__(self, source, policy: PrecipitationPolicy | None = None, trend_policy: TrendPolicy | None = None) -> None:
        self._source = source
        self._policy = policy or PrecipitationPolicy()
        self._trend_policy = trend_policy or TrendPolicy()

    def fetch(self, query: PrecipitationQuery) -> MonthlyPrecipitationSeries:
        return self._source.fetch_monthly(query)

    def analyze(self, query: PrecipitationQuery, include_relative_change: bool = False) -> PrecipitationAnalysis:
        series = self.fetch(query)
        annual = aggregate_precipitation_years(series, query, self._policy)
        shared = tuple(self._to_shared(item) for item in annual)
        trend = analyze_trend(shared, "mm/year", self._trend_policy)
        # The shared engine appends '/year'; render the physical dimension explicitly.
        if trend.theil_sen is not None:
            trend = replace(trend, theil_sen=replace(trend.theil_sen, slope_units="mm/year²"))
        slope = trend.theil_sen.slope if trend.theil_sen else None
        reference = relative = None
        eligible = [item.annual_accumulation_mm for item in annual if item.eligible_for_trend_inference and item.annual_accumulation_mm is not None]
        if include_relative_change and slope is not None and eligible:
            reference = float(median(eligible))
            if reference > 0:
                relative = slope / reference * 100
        return PrecipitationAnalysis(series, annual, trend, slope, relative, reference)

    @staticmethod
    def _to_shared(item: AnnualPrecipitationSummary) -> AnnualSummary:
        quarters = tuple(sorted({(month - 1) // 3 + 1 for month in item.represented_months}))
        return AnnualSummary(
            year=item.year,
            annual_value=item.annual_accumulation_mm,
            value_units="mm/year",
            monthly_values=item.monthly_accumulations,
            represented_months=item.represented_months,
            missing_months=item.missing_months,
            represented_quarters=quarters,
            missing_quarters=tuple(q for q in range(1, 5) if q not in quarters),
            valid_observations=item.valid_months,
            used_observations=item.valid_months,
            expected_observations=12,
            available_images=item.catalog_months,
            valid_coverage_percentage=item.valid_coverage_percentage,
            image_availability_percentage=item.catalog_coverage_percentage,
            is_complete_calendar_year=item.is_complete_calendar_year,
            eligible_for_trend_inference=item.eligible_for_trend_inference,
            eligibility_reasons=item.eligibility_reasons,
            minimum_spatial_coverage_percentage=None,
            mean_spatial_coverage_percentage=None,
            median_spatial_coverage_percentage=None,
            spatial_coverage_threshold_applied=None,
        )

