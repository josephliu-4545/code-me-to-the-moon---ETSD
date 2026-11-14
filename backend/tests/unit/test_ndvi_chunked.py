from datetime import date

from app.schemas.ndvi import NDVIQuery
from app.services.ndvi_chunked import YearChunkedNDVIProvider, year_windows
from app.statistics.models import ObservationSeries, TimedValue, YearCoverage


def test_year_windows_split_on_calendar_years() -> None:
    assert year_windows(date(2015, 6, 1), date(2017, 3, 1)) == [
        (date(2015, 6, 1), date(2016, 1, 1)), (date(2016, 1, 1), date(2017, 1, 1)), (date(2017, 1, 1), date(2017, 3, 1)),
    ]


def test_chunked_provider_merges_yearly_series_in_order() -> None:
    class Provider:
        def fetch_ndvi_series(self, query):
            year = query.start_date.year
            day = date(year, 1, 1)
            return ObservationSeries("NDVI", "NDVI units", "MOD13Q1", (TimedValue(day, 0.5),),
                                     (YearCoverage(year, (day,), (day,), True),))

    query = NDVIQuery(latitude=0, longitude=0, start_date=date(2001, 1, 1), end_date=date(2004, 1, 1))
    series = YearChunkedNDVIProvider(Provider()).fetch_ndvi_series(query)
    assert [c.year for c in series.coverage_by_year] == [2001, 2002, 2003]
    assert [o.date.year for o in series.observations] == [2001, 2002, 2003]
