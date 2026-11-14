from datetime import date

import pytest

from app.schemas.ndvi import NDVIQuery
from app.services.modis_service import (
    ModisService,
    build_good_quality_support,
    calculate_spatial_coverage_percentage,
)


class TraceBand:
    def __init__(self, actions: list[tuple[object, ...]], band: str) -> None:
        self.actions = actions
        self.band = band

    def eq(self, value: int) -> "TraceBand":
        self.actions.append(("eq", self.band, value))
        return self

    def mask(self) -> "TraceBand":
        self.actions.append(("mask", self.band))
        return self

    def And(self, other: "TraceBand") -> "TraceBand":
        self.actions.append(("and", self.band, other.band))
        return self

    def unmask(self, value: int) -> "TraceBand":
        self.actions.append(("unmask", self.band, value))
        return self

    def rename(self, name: str) -> "TraceBand":
        self.actions.append(("rename", self.band, name))
        return self


class TraceImage:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []

    def select(self, band: str) -> TraceBand:
        self.actions.append(("select", band))
        return TraceBand(self.actions, band)


def query(radius_km: float) -> NDVIQuery:
    return NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=radius_km,
    )


def test_support_numerator_and_denominator_share_modis_derived_grid() -> None:
    image = TraceImage()

    build_good_quality_support(image)

    assert image.actions == [
        ("select", "SummaryQA"),
        ("eq", "SummaryQA", 0),
        ("select", "NDVI"),
        ("mask", "NDVI"),
        ("and", "SummaryQA", "NDVI"),
        ("unmask", "SummaryQA", 0),
        ("rename", "SummaryQA", "support"),
    ]


@pytest.mark.parametrize(
    ("valid_pixels", "total_pixels", "expected"),
    [(100, 100, 100.0), (25, 100, 25.0), (0, 100, 0.0)],
)
def test_spatial_percentage_for_full_partial_and_masked_coverage(
    valid_pixels: int,
    total_pixels: int,
    expected: float,
) -> None:
    assert calculate_spatial_coverage_percentage(valid_pixels, total_pixels) == expected


def test_zero_denominator_returns_unavailable_instead_of_dividing() -> None:
    assert calculate_spatial_coverage_percentage(0, 0) is None


def test_original_grid_inconsistency_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_spatial_coverage_percentage(1292, 1243)


@pytest.mark.parametrize(
    ("radius_km", "valid_pixels", "total_pixels"),
    [(1, 20, 40), (5, 500, 1000), (7.25, 777, 1554)],
)
def test_different_radii_and_boundary_pixel_counts_stay_bounded(
    radius_km: float,
    valid_pixels: int,
    total_pixels: int,
) -> None:
    series = ModisService._series_from_rows(
        query(radius_km),
        [["2020-01-01", 0.5, valid_pixels, total_pixels]],
    )
    percentage = series.observations[0].spatial_coverage_percentage
    assert percentage == 50.0
    assert 0 <= percentage <= 100


def test_fully_masked_available_image_is_not_a_valid_observation() -> None:
    series = ModisService._series_from_rows(
        query(5), [["2020-01-01", None, 0, 1000]]
    )
    assert len(series.coverage_by_year[0].available_image_dates) == 1
    assert series.observations == ()


def test_zero_denominator_valid_mean_keeps_value_with_unknown_spatial_support() -> None:
    series = ModisService._series_from_rows(
        query(5), [["2020-01-01", 0.5, 0, 0]]
    )
    observation = series.observations[0]
    assert observation.value == 0.5
    assert observation.spatial_coverage_percentage is None
    assert observation.valid_pixel_count is None
    assert observation.total_pixel_count is None

