from datetime import date

import pytest

from app.comparison.catalog import find
from app.comparison.evaluation import evaluate_dataset


ERA5 = find("temperature", "era5_land_t2m")
POWER = find("temperature", "nasa_power_t2m")


def test_monthly_coverage_distinguishes_supported_statuses_and_denominator() -> None:
    analysis = {
        "series": [
            {"date": "1950-01-01", "value": 20.0, "status": "valid", "usable": True},
            {"date": "1950-02-01", "value": None, "status": "no_images", "usable": False},
            {"date": "1950-03-01", "value": None, "status": "invalid_values", "usable": False},
            {"date": "1950-04-01", "value": 21.0, "status": "valid", "usable": False, "provisional": True},
        ],
        "annual": [],
        "coverage": {"eligible_years": 0, "excluded_years": []},
    }

    result = evaluate_dataset(ERA5, analysis, date(1949, 12, 1), date(1950, 5, 1))

    assert result["resolution"] == "monthly"
    assert [cell["status"] for cell in result["cells"]] == [
        "outside_coverage", "valid", "missing", "excluded", "provisional"
    ]
    assert result["completeness"] == {
        "valid": 1,
        "expected_within_supported_coverage": 4,
        "percentage": 25.0,
        "label": "Valid months / Expected months within supported dataset coverage",
    }
    assert result["counts"] == {"valid": 1, "missing": 1, "excluded": 1, "provisional": 1, "outside_coverage": 1, "unavailable": 0}


def test_annual_fallback_preserves_exclusion_reasons_and_missing_is_not_zero() -> None:
    analysis = {
        "series": [],
        "annual": [
            {"year": 2019, "value": 27.0, "eligible": True, "reasons": []},
            {"year": 2020, "value": 28.0, "eligible": False, "reasons": ["insufficient_represented_months"]},
            {"year": 2021, "value": None, "eligible": False, "reasons": ["no_valid_observations"]},
        ],
        "coverage": {"eligible_years": 1, "excluded_years": []},
    }

    result = evaluate_dataset(POWER, analysis, date(2019, 1, 1), date(2022, 1, 1))

    assert result["resolution"] == "annual"
    assert result["resolution_note"] == "Annual coverage: monthly quality-control information is not available for this dataset response."
    assert [cell["status"] for cell in result["cells"]] == ["valid", "excluded", "missing"]
    assert result["cells"][1]["reasons"] == ["insufficient_represented_months"]
    assert result["cells"][2]["value"] is None
    assert result["completeness"]["valid"] == 1
    assert result["completeness"]["expected_within_supported_coverage"] == 3
    assert result["completeness"]["percentage"] == pytest.approx(100 / 3)


def test_unavailable_dataset_still_reports_requested_period_without_fabricated_values() -> None:
    result = evaluate_dataset(POWER, None, date(2019, 1, 1), date(2021, 1, 1))

    assert result["resolution"] == "annual"
    assert [cell["status"] for cell in result["cells"]] == ["unavailable", "unavailable"]
    assert result["completeness"]["valid"] == 0
    assert result["completeness"]["expected_within_supported_coverage"] == 2
    assert result["completeness"]["percentage"] == 0.0


def test_catalog_end_date_is_inclusive_for_supported_annual_denominator() -> None:
    retired = find("soil_moisture", "smap_l3e_v005_am")
    analysis = {
        "series": [],
        "annual": [{"year": 2023, "value": 0.2, "eligible": True, "reasons": []}],
        "coverage": {"eligible_years": 1, "excluded_years": []},
    }

    result = evaluate_dataset(retired, analysis, date(2023, 1, 1), date(2025, 1, 1))

    assert [cell["status"] for cell in result["cells"]] == ["valid", "outside_coverage"]
    assert result["completeness"]["expected_within_supported_coverage"] == 1
    assert result["supported_period"]["end"] == "2023-12-02"
