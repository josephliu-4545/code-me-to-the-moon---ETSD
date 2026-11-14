from datetime import date

import pytest

from app.schemas.ndvi import NDVIQuery
from app.services.modis_service import ModisService


def test_series_normalization_distinguishes_available_valid_and_spatial_coverage() -> None:
    query = NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=5,
    )
    rows = [
        ["2020-01-01", 0.52, 80, 100],
        ["2020-01-17", None, 0, 100],
        ["2020-02-02", 0.61, 50, 100],
    ]

    series = ModisService._series_from_rows(query, rows)

    coverage = series.coverage_by_year[0]
    assert len(coverage.expected_slot_dates) == 23
    assert coverage.available_image_dates == (
        date(2020, 1, 1), date(2020, 1, 17), date(2020, 2, 2)
    )
    assert coverage.is_complete_calendar_year is True
    assert len(series.observations) == 2
    assert series.observations[0].spatial_coverage_percentage == 80.0
    assert series.observations[1].spatial_coverage_percentage == 50.0


def test_series_marks_partial_calendar_year() -> None:
    query = NDVIQuery(
        latitude=0,
        longitude=0,
        start_date=date(2020, 3, 1),
        end_date=date(2021, 1, 1),
        radius_km=1,
    )
    series = ModisService._series_from_rows(
        query, [["2020-03-05", 0.4, 10, 20]]
    )
    assert series.coverage_by_year[0].is_complete_calendar_year is False


def test_series_rejects_malformed_pixel_counts() -> None:
    query = NDVIQuery(
        latitude=0,
        longitude=0,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=1,
    )
    with pytest.raises(ValueError, match="pixel"):
        ModisService._series_from_rows(query, [["2020-01-01", 0.4, 30, 20]])

