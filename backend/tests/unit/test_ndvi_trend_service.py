from datetime import date

from app.core.config import Settings
from app.schemas.ndvi import NDVIQuery
from app.services.modis_service import ModisService
from app.services.ndvi_trend_service import NDVITrendService


class SeriesProvider:
    def __init__(self, series: object) -> None:
        self.series = series

    def fetch_ndvi_series(self, query: NDVIQuery) -> object:
        return self.series


def test_yangon_2020_returns_summary_and_explicit_exclusions() -> None:
    query = NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=5,
    )
    dates = (
        "2020-01-01", "2020-01-17", "2020-02-02", "2020-02-18",
        "2020-03-05", "2020-03-21", "2020-04-06", "2020-04-22",
        "2020-05-08", "2020-10-31", "2020-11-16", "2020-12-02",
        "2020-12-18",
    )
    rows = [[day, 0.5, 80, 100] for day in dates]
    series = ModisService._series_from_rows(query, rows)
    service = NDVITrendService(SeriesProvider(series), Settings())

    response = service.analyze(query)

    assert response.observation_count == 13
    assert response.eligible_annual_observation_count == 0
    assert len(response.annual_summaries) == 1
    summary = response.annual_summaries[0]
    assert summary.year == 2020
    assert summary.annual_value == 0.5
    assert summary.valid_coverage_percentage == 13 / 23 * 100
    assert summary.eligible_for_trend_inference is False
    assert summary.eligibility_reasons == [
        "insufficient_represented_months",
        "insufficient_valid_slot_coverage",
        "missing_calendar_quarter",
    ]
    assert response.trend.result_level == "annual_summaries_only"
    assert response.trend.significance_unavailable_reason is not None
    assert response.methodology["thresholds_are_universal_standards"] is False
    assert any("independence" in item.lower() for item in response.limitations)

