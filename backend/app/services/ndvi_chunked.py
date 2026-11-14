"""Fetch long NDVI series as one Earth Engine request per calendar year, in parallel.

A single multi-decade MODIS request is slow and can exceed the request timeout; yearly
windows are small and independent. Each window's coverage describes only its own year,
so concatenating windows gives the same ObservationSeries as one request would.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from app.schemas.ndvi import NDVIQuery
from app.services.ndvi_trend_service import NDVISeriesProvider
from app.statistics.models import ObservationSeries


def year_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end) at calendar-year boundaries."""
    windows, cursor = [], start
    while cursor < end:
        boundary = min(date(cursor.year + 1, 1, 1), end)
        windows.append((cursor, boundary))
        cursor = boundary
    return windows


class YearChunkedNDVIProvider:
    def __init__(self, provider: NDVISeriesProvider, max_workers: int = 4) -> None:
        self._provider = provider
        self._max_workers = max_workers

    def fetch_ndvi_series(self, query: NDVIQuery) -> ObservationSeries:
        queries = [query.model_copy(update={"start_date": s, "end_date": e}) for s, e in year_windows(query.start_date, query.end_date)]
        with ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="ndvi-year") as pool:
            parts = list(pool.map(self._provider.fetch_ndvi_series, queries))
        first = parts[0]
        return ObservationSeries(
            variable=first.variable,
            value_units=first.value_units,
            dataset=first.dataset,
            observations=tuple(o for part in parts for o in part.observations),
            coverage_by_year=tuple(c for part in parts for c in part.coverage_by_year),
        )
