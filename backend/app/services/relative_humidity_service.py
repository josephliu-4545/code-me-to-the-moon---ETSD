from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import math
from statistics import mean

from app.power.client import PowerClient
from app.power.models import PowerParameter, PowerPayload, PowerPointQuery
from app.statistics.models import AnnualSummary, TimedValue, TrendAnalysisResult
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


class RelativeHumidityDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class RelativeHumidityPolicy:
    minimum_annual_coverage: float = 0.90
    minimum_monthly_coverage: float = 0.80
    require_all_months: bool = True
    exclude_partial_calendar_years: bool = True


@dataclass(frozen=True)
class RelativeHumiditySeries:
    observations: tuple[TimedValue, ...]
    expected_count: int
    returned_count: int
    valid_count: int
    missing_dates: tuple[date, ...]
    units: str
    time_standard: str
    temporal_resolution: str = "daily"
    returned_dates: tuple[date, ...] = ()


@dataclass(frozen=True)
class RelativeHumidityTrendResult:
    series: RelativeHumiditySeries
    annual_summaries: tuple[AnnualSummary, ...]
    trend: TrendAnalysisResult


class RelativeHumidityService:
    def __init__(
        self,
        client: PowerClient,
        policy: RelativeHumidityPolicy | None = None,
        trend_policy: TrendPolicy | None = None,
    ) -> None:
        self._client = client
        self._policy = policy or RelativeHumidityPolicy()
        self._trend_policy = trend_policy or TrendPolicy()

    def fetch_daily(self, query: PowerPointQuery) -> RelativeHumiditySeries:
        return self._parse_daily(self._client.fetch_daily_point(query, PowerParameter.RH2M), query)

    def fetch_monthly(self, query: PowerPointQuery) -> RelativeHumiditySeries:
        payload = self._client.fetch_monthly_point(query, PowerParameter.RH2M)
        self._validate_units(payload.units)
        observations: list[TimedValue] = []
        returned = 0
        for key, raw in payload.values.items():
            if len(key) != 6:
                continue
            try:
                year, month = int(key[:4]), int(key[4:])
                if not 1 <= month <= 12:
                    continue
                period = date(year, month, 1)
            except (TypeError, ValueError):
                raise RelativeHumidityDataError("invalid monthly period") from None
            if not query.start_date <= period < query.end_date:
                continue
            returned += 1
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise RelativeHumidityDataError("RH2M value is not numeric") from None
            if value == -999 or value == payload.fill_value:
                continue
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise RelativeHumidityDataError("RH2M value is outside 0-100 percent")
            observations.append(TimedValue(period, value))
        expected_dates: list[date] = []
        cursor = date(query.start_date.year, query.start_date.month, 1)
        while cursor < query.end_date:
            if cursor >= query.start_date:
                expected_dates.append(cursor)
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        valid_dates = {item.date for item in observations}
        returned_dates = tuple(
            date(int(key[:4]), int(key[4:]), 1)
            for key in payload.values
            if len(key) == 6 and key[4:].isdigit() and 1 <= int(key[4:]) <= 12
            and query.start_date <= date(int(key[:4]), int(key[4:]), 1) < query.end_date
        )
        return RelativeHumiditySeries(tuple(observations), len(expected_dates), returned, len(observations), tuple(day for day in expected_dates if day not in valid_dates), "%", payload.time_standard or query.time_standard, "monthly", returned_dates)

    def analyze(self, query: PowerPointQuery) -> RelativeHumidityTrendResult:
        series = self.fetch_daily(query)
        summaries = self._aggregate(series, query)
        trend = analyze_trend(summaries, "percentage points", self._trend_policy)
        return RelativeHumidityTrendResult(series, summaries, trend)

    @staticmethod
    def _validate_units(units: str | None) -> None:
        if units not in {"%", "percent", "Percent"}:
            raise RelativeHumidityDataError("RH2M units must be percent")

    def _parse_daily(self, payload: PowerPayload, query: PowerPointQuery) -> RelativeHumiditySeries:
        self._validate_units(payload.units)
        expected: list[date] = []
        cursor = query.start_date
        while cursor < query.end_date:
            expected.append(cursor)
            cursor += timedelta(days=1)
        expected_set = set(expected)
        returned_dates: set[date] = set()
        observations: list[TimedValue] = []
        sentinels = {-999, -999.0}
        if payload.fill_value is not None:
            try:
                sentinels.add(float(payload.fill_value))
            except (TypeError, ValueError):
                pass
        for key, raw in payload.values.items():
            try:
                day = date.fromisoformat(f"{key[:4]}-{key[4:6]}-{key[6:8]}")
            except (ValueError, TypeError):
                raise RelativeHumidityDataError("invalid observation date") from None
            if day not in expected_set or day in returned_dates:
                raise RelativeHumidityDataError("duplicate or out-of-range observation date")
            returned_dates.add(day)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise RelativeHumidityDataError("RH2M value is not numeric") from None
            if value in sentinels:
                continue
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise RelativeHumidityDataError("RH2M value is outside 0-100 percent")
            observations.append(TimedValue(day, value))
        valid_dates = {item.date for item in observations}
        return RelativeHumiditySeries(
            observations=tuple(sorted(observations, key=lambda item: item.date)),
            expected_count=len(expected),
            returned_count=len(returned_dates),
            valid_count=len(observations),
            missing_dates=tuple(day for day in expected if day not in valid_dates),
            units="%",
            time_standard=payload.time_standard or query.time_standard,
            returned_dates=tuple(sorted(returned_dates)),
        )

    def _aggregate(self, series: RelativeHumiditySeries, query: PowerPointQuery) -> tuple[AnnualSummary, ...]:
        by_year: dict[int, list[TimedValue]] = defaultdict(list)
        for item in series.observations:
            by_year[item.date.year].append(item)
        summaries: list[AnnualSummary] = []
        for year in range(query.start_date.year, (query.end_date - timedelta(days=1)).year + 1):
            year_start, year_end = date(year, 1, 1), date(year + 1, 1, 1)
            interval_start, interval_end = max(query.start_date, year_start), min(query.end_date, year_end)
            expected = (interval_end - interval_start).days
            complete = interval_start == year_start and interval_end == year_end
            items = by_year.get(year, [])
            monthly_items: dict[int, list[float]] = defaultdict(list)
            for item in items:
                monthly_items[item.date.month].append(item.value)
            monthly_values = tuple((month, mean(values)) for month, values in sorted(monthly_items.items()))
            represented: list[int] = []
            inadequate: list[int] = []
            for month in range(1, 13):
                month_start = date(year, month, 1)
                month_end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
                expected_month = max(0, (min(interval_end, month_end) - max(interval_start, month_start)).days)
                if expected_month == 0:
                    continue
                fraction = len(monthly_items[month]) / expected_month if expected_month > 0 else 0
                if fraction >= self._policy.minimum_monthly_coverage:
                    represented.append(month)
                else:
                    inadequate.append(month)
            missing_months = tuple(month for month in range(1, 13) if month not in represented)
            valid_fraction = len(items) / expected if expected else 0.0
            reasons: list[str] = []
            if self._policy.exclude_partial_calendar_years and not complete:
                reasons.append("partial_calendar_year")
            if not items:
                reasons.append("no_valid_observations")
            if self._policy.require_all_months and len(represented) < 12:
                reasons.append("insufficient_represented_months")
            if inadequate:
                reasons.append("insufficient_monthly_coverage")
            if valid_fraction < self._policy.minimum_annual_coverage:
                reasons.append("insufficient_annual_coverage")
            summaries.append(AnnualSummary(
                year=year,
                annual_value=mean(value for _, value in monthly_values) if monthly_values else None,
                value_units="%",
                monthly_values=monthly_values,
                represented_months=tuple(represented),
                missing_months=missing_months,
                represented_quarters=tuple(sorted({(month - 1) // 3 + 1 for month in represented})),
                missing_quarters=(),
                valid_observations=len(items),
                used_observations=len(items),
                expected_observations=expected,
                available_images=sum(day.year == year for day in series.returned_dates),
                valid_coverage_percentage=valid_fraction * 100,
                image_availability_percentage=valid_fraction * 100,
                is_complete_calendar_year=complete,
                eligible_for_trend_inference=not reasons,
                eligibility_reasons=tuple(reasons),
                minimum_spatial_coverage_percentage=None,
                mean_spatial_coverage_percentage=None,
                median_spatial_coverage_percentage=None,
                spatial_coverage_threshold_applied=None,
            ))
        return tuple(summaries)
