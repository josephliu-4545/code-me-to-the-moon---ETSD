from datetime import date

from app.precipitation.aggregation import monthly_rate_to_accumulation
from app.precipitation.models import MonthlyPrecipitation, MonthlyPrecipitationSeries, PrecipitationQuery
from app.services.precipitation_service import PrecipitationService


class Source:
    def fetch_monthly(self, query):
        rows = tuple(
            MonthlyPrecipitation(date(year, month, 1), float(year - 2019), monthly_rate_to_accumulation(float(year - 2019), year, month), True)
            for year in range(2020, 2023) for month in range(1, 13)
        )
        return MonthlyPrecipitationSeries(rows, "cell")


def test_service_reuses_shared_trend_engine_and_units() -> None:
    result = PrecipitationService(Source()).analyze(
        PrecipitationQuery(0, 0, date(2020, 1, 1), date(2023, 1, 1))
    )
    assert len(result.annual_summaries) == 3
    assert result.trend.result_level == "descriptive_slope"
    assert result.trend.theil_sen is not None
    assert result.trend.theil_sen.slope_units == "mm/year²"
    assert result.annual_total_change_mm_per_calendar_year == result.trend.theil_sen.slope


def test_partial_year_summary_is_preserved() -> None:
    result = PrecipitationService(Source()).analyze(
        PrecipitationQuery(0, 0, date(2020, 2, 1), date(2021, 1, 1))
    )
    assert result.annual_summaries[0].annual_accumulation_mm is None
    assert result.annual_summaries[0].observed_accumulation_mm > 0
    assert result.annual_summaries[0].eligible_for_trend_inference is False
    assert result.trend.result_level == "annual_summaries_only"

