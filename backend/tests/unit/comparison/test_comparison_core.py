from datetime import date, timedelta

import pytest

from app.comparison.catalog import CATALOG, NOT_YET_COMPARABLE, entries, find, relationship
from app.comparison.engine import agreement_summary, compare, compare_pair
from app.comparison.providers import (
    ComparisonRetrievalError,
    EEMonthlyProvider,
    analyze_months,
    annual_summaries,
    expected_samples,
    native_cell,
    normalize_rows,
)
from app.services.soil_moisture_provider import UnsupportedLocationError


T_GLDAS = find("temperature", "gldas_2_1_tair")
T_ERA5 = find("temperature", "era5_land_t2m")
P_CHIRPS = find("precipitation", "chirps_v2_daily")
P_ERA5 = find("precipitation", "era5_land_tp")


def months(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def rows_for(entry, start, end, native=300.0, skip=(), invalid=(), early=(), short=()):
    rows = []
    for m in months(start, end):
        if m in skip:
            continue
        n = expected_samples(entry, m)
        valid = n - 1 if m in invalid else (int(n * 0.5) if m in short else n)
        raw = n if m in invalid else valid
        images = n if entry.method in ("subdaily_mean", "daily_sum") else 1
        permanent = 0 if m in early else images
        rows.append([m.isoformat(), images, raw, valid, native, permanent, images])
    return rows


# --- catalog -------------------------------------------------------------------


def test_catalog_lists_primaries_first_and_verified_fields() -> None:
    for variable, items in CATALOG.items():
        assert len(items) >= 2, variable
        assert sum(e.is_primary for e in items) == 1
        assert items[0].is_primary
        keys = [e.key for e in items]
        assert len(keys) == len(set(keys))
        for e in items:
            assert e.collection_id and e.citation and e.license and e.limitations and e.quality_control
            assert e.backend in ("v1", "ee_monthly")
            if e.backend == "ee_monthly":
                assert e.band and e.crs_transform and e.method


def test_variables_without_alternatives_explain_why() -> None:
    assert set(NOT_YET_COMPARABLE) == {"relative_humidity", "extreme_heat", "ndvi"}
    assert entries("ndvi") == ()


def test_lineage_classification() -> None:
    assert relationship(find("soil_moisture", "smap_l3e_v005_am"), find("soil_moisture", "smap_l3e_v006_am"))[0] == "same_lineage"
    assert relationship(find("precipitation", "gpm_imerg_v07"), P_CHIRPS)[0] == "partially_related"
    assert relationship(find("precipitation", "gpm_imerg_v07"), P_ERA5)[0] == "independent"
    assert relationship(find("temperature", "nasa_power_t2m"), T_ERA5)[0] == "partially_related"


def test_temperature_alternatives_convert_kelvin_and_soil_quantities_differ() -> None:
    assert T_GLDAS.offset == -273.15 and T_ERA5.offset == -273.15 and T_GLDAS.units == "°C"
    gldas_sm, smap = find("soil_moisture", "gldas_2_1_noah_0_10cm"), find("soil_moisture", "smap_l3e_v006_am")
    assert gldas_sm.comparable_quantity != smap.comparable_quantity


# --- cells and coverage -----------------------------------------------------------


def test_native_cells_follow_each_grid() -> None:
    c = native_cell(T_GLDAS, 16.8661, 96.1951)
    assert c.center == (16.875, 96.125) and (c.south, c.north) == (16.75, 17.0)
    e = native_cell(T_ERA5, 16.8661, 96.1951)
    assert e.size_degrees == 0.1 and e.south <= 16.8661 < e.north and e.west <= 96.1951 < e.east
    ch = native_cell(P_CHIRPS, -1.3, 36.8)
    assert ch.size_degrees == 0.05 and ch.south <= -1.3 < ch.north


def test_expected_samples_by_method() -> None:
    assert expected_samples(T_GLDAS, date(2020, 2, 1)) == 29 * 8
    assert expected_samples(T_GLDAS, date(2000, 1, 1)) == 247
    assert expected_samples(P_CHIRPS, date(2021, 2, 1)) == 28
    assert expected_samples(T_ERA5, date(2021, 2, 1)) == 1


# --- normalisation ------------------------------------------------------------------


def test_valid_months_convert_units() -> None:
    out = normalize_rows(T_GLDAS, rows_for(T_GLDAS, date(2020, 1, 1), date(2020, 3, 1), native=300.0), date(2020, 1, 1), date(2020, 3, 1))
    assert [m.status for m in out] == ["valid", "valid"]
    assert out[0].value == pytest.approx(26.85)


def test_precipitation_scaling_and_sums() -> None:
    era = normalize_rows(P_ERA5, rows_for(P_ERA5, date(2020, 1, 1), date(2020, 2, 1), native=0.25), date(2020, 1, 1), date(2020, 2, 1))
    assert era[0].value == pytest.approx(250.0)


@pytest.mark.parametrize(
    "kwargs, status",
    [
        ({"skip": {date(2020, 1, 1)}}, "no_images"),
        ({"invalid": {date(2020, 1, 1)}}, "invalid_values"),
        ({"short": {date(2020, 1, 1)}}, "insufficient_coverage"),
    ],
)
def test_month_statuses_are_missing_never_zero(kwargs, status) -> None:
    (m,) = normalize_rows(T_GLDAS, rows_for(T_GLDAS, date(2020, 1, 1), date(2020, 2, 1), **kwargs), date(2020, 1, 1), date(2020, 2, 1))
    assert m.status == status and m.value is None and not m.usable


def test_chirps_month_needs_every_day() -> None:
    rows = rows_for(P_CHIRPS, date(2020, 1, 1), date(2020, 2, 1), native=10.0)
    rows[0][3] = 30  # one day missing (raw also 30 → not invalid, just incomplete)
    rows[0][2] = 30
    (m,) = normalize_rows(P_CHIRPS, rows, date(2020, 1, 1), date(2020, 2, 1))
    assert m.status == "insufficient_coverage"


def test_negative_era5_precipitation_invalidates_the_month() -> None:
    rows = [["2020-01-01", 1, 1, 0, None, 1, 1]]
    (m,) = normalize_rows(P_ERA5, rows, date(2020, 1, 1), date(2020, 2, 1))
    assert m.status == "invalid_values" and m.value is None


def test_early_stream_months_are_provisional() -> None:
    (m,) = normalize_rows(T_GLDAS, rows_for(T_GLDAS, date(2020, 1, 1), date(2020, 2, 1), early={date(2020, 1, 1)}), date(2020, 1, 1), date(2020, 2, 1))
    assert m.status == "valid" and m.provisional and not m.usable


@pytest.mark.parametrize(
    "rows, message",
    [
        ("x", "malformed provider response"),
        ([["2020-01-01", 1]], "malformed provider row"),
        ([["2020-13-01", 1, 1, 1, 1, 1, 1]], "invalid month"),
        ([["2020-01-01", 1, 1, 1, 1.0, 1, 1]] * 2, "duplicate"),
        ([["2020-01-01", 1, 2, 3, 1.0, 1, 1]], "inconsistent"),
        ([["2020-01-01", -1, 0, 0, None, 0, 0]], "invalid provider counts"),
    ],
)
def test_malformed_rows_are_rejected(rows, message) -> None:
    with pytest.raises(ComparisonRetrievalError, match=message):
        normalize_rows(T_ERA5, rows, date(2020, 1, 1), date(2020, 2, 1))


# --- annual aggregation ---------------------------------------------------------------


def test_annual_mean_and_eligibility() -> None:
    ms = normalize_rows(T_ERA5, rows_for(T_ERA5, date(2019, 7, 1), date(2021, 1, 1), native=300.0), date(2019, 7, 1), date(2021, 1, 1))
    y2019, y2020 = annual_summaries(T_ERA5, ms)
    assert not y2019.eligible_for_trend_inference and "partial_calendar_year" in y2019.eligibility_reasons
    assert y2019.annual_value == pytest.approx(26.85)  # descriptive mean of the months present
    assert y2020.eligible_for_trend_inference and y2020.annual_value == pytest.approx(26.85)


def test_annual_sum_requires_twelve_months() -> None:
    start, end = date(2020, 1, 1), date(2021, 1, 1)
    full = annual_summaries(P_ERA5, normalize_rows(P_ERA5, rows_for(P_ERA5, start, end, native=0.1), start, end))[0]
    assert full.annual_value == pytest.approx(1200.0) and full.eligible_for_trend_inference
    gap = annual_summaries(P_ERA5, normalize_rows(P_ERA5, rows_for(P_ERA5, start, end, native=0.1, skip={date(2020, 5, 1)}), start, end))[0]
    assert gap.annual_value is None and "insufficient_represented_months" in gap.eligibility_reasons


def test_trend_units_for_sums_and_means() -> None:
    start, end = date(2010, 1, 1), date(2020, 1, 1)
    _, t = analyze_months(P_ERA5, normalize_rows(P_ERA5, rows_for(P_ERA5, start, end, native=0.1), start, end))
    assert t.theil_sen.slope_units == "mm/year²"
    _, t2 = analyze_months(T_ERA5, normalize_rows(T_ERA5, rows_for(T_ERA5, start, end, native=290.0), start, end))
    assert t2.theil_sen.slope_units == "°C/year"


# --- provider ---------------------------------------------------------------------------


class FakeManager:
    ee = None

    def initialize(self) -> None:
        pass


def test_provider_windows_cache_and_coverage_limits() -> None:
    calls = []

    def loader(entry, cell, s, e):
        calls.append((s, e))
        return rows_for(entry, s, e)

    p = EEMonthlyProvider(FakeManager(), loader=loader)
    r1 = p.fetch(T_ERA5, 16.8661, 96.1951, date(2010, 1, 1), date(2020, 1, 1))
    p.fetch(T_ERA5, 16.8661, 96.1951, date(2010, 1, 1), date(2020, 1, 1))
    assert sorted(calls) == [(date(2010, 1, 1), date(2015, 1, 1)), (date(2015, 1, 1), date(2020, 1, 1))]
    assert len(r1.months) == 120
    with pytest.raises(UnsupportedLocationError):
        p.fetch(P_CHIRPS, 60.0, 25.0, date(2010, 1, 1), date(2011, 1, 1))
    with pytest.raises(UnsupportedLocationError):
        p.fetch(T_GLDAS, -70.0, 0.0, date(2010, 1, 1), date(2011, 1, 1))


def test_provider_wraps_unexpected_errors() -> None:
    def boom(*a):
        raise RuntimeError("secret detail")
    with pytest.raises(ComparisonRetrievalError) as exc:
        EEMonthlyProvider(FakeManager(), loader=boom).fetch(T_ERA5, 0, 0, date(2010, 1, 1), date(2011, 1, 1))
    assert "secret" not in str(exc.value)


# --- engine ---------------------------------------------------------------------------------


def analysis(values: dict[int, float | None], units="°C", slope=0.1, ci=None, eligible=None):
    eligible = eligible if eligible is not None else {y for y, v in values.items() if v is not None}
    return {
        "units": {"annual_value": units},
        "annual": [{"year": y, "value": v, "eligible": y in eligible} for y, v in sorted(values.items())],
        "trend": {"slope": slope, "confidence_interval": ci},
    }


def test_pair_differences_correlations_and_common_period() -> None:
    years = range(2010, 2020)
    a = analysis({y: 20 + 0.1 * (y - 2010) + (0.2 if y % 2 else 0) for y in years}, slope=0.1, ci=[0.05, 0.15])
    b = analysis({y: 19 + 0.1 * (y - 2010) + (0.2 if y % 2 else 0) for y in years}, slope=0.12, ci=[0.08, 0.2])
    p = compare_pair(find("temperature", "nasa_power_t2m"), T_ERA5, a, b)
    assert p["numerically_comparable"] and p["mean_difference"] == pytest.approx(1.0)
    assert p["spearman_rho"] == pytest.approx(1.0) and p["slope_sign_agreement"] is True
    assert p["confidence_intervals_overlap"] is True
    assert p["common_period_slopes"]["nasa_power_t2m"] == pytest.approx(0.1, abs=0.05)
    assert "not an error" in p["difference_label"]
    assert p["root_mean_square_difference"] == pytest.approx(1.0)
    assert p["slope_difference"] == pytest.approx(
        p["common_period_slopes"]["nasa_power_t2m"] - p["common_period_slopes"]["era5_land_t2m"]
    )
    assert p["matched_observations"] == {
        "resolution": "annual",
        "count": 10,
        "period": {"start": "2010", "end": "2019"},
        "labels": [str(y) for y in years],
        "valid_observations": {
            "nasa_power_t2m": [str(y) for y in years],
            "era5_land_t2m": [str(y) for y in years],
        },
        "excluded_from_pairing": {"nasa_power_t2m": [], "era5_land_t2m": []},
        "quality_excluded": {"nasa_power_t2m": [], "era5_land_t2m": []},
    }
    rmse = next(m for m in p["metrics"] if m["id"] == "rmse")
    assert rmse["value"] == pytest.approx(1.0)
    assert rmse["units"] == "°C" and rmse["matched_observations"] == 10
    assert "product-to-product" in rmse["interpretation"]
    assert "ground truth" in rmse["limitations"]


def test_pair_withholds_correlation_below_eight_common_years() -> None:
    a = analysis({y: 1.0 * y for y in range(2010, 2016)})
    b = analysis({y: 2.0 * y for y in range(2010, 2016)})
    p = compare_pair(find("temperature", "nasa_power_t2m"), T_ERA5, a, b)
    assert p["spearman_rho"] is None and "fewer_than_8_common_eligible_years_for_correlation" in p["unavailable_reasons"]
    spearman = next(m for m in p["metrics"] if m["id"] == "spearman_rho")
    assert spearman["value"] is None
    assert spearman["availability"] == "unavailable"
    assert "8 common eligible years" in spearman["unavailable_reason"]


def test_non_comparable_quantities_are_not_differenced() -> None:
    gldas, smap = find("soil_moisture", "gldas_2_1_noah_0_10cm"), find("soil_moisture", "smap_l3e_v006_am")
    p = compare_pair(gldas, smap, analysis({y: 25.0 for y in range(2015, 2025)}, units="kg m-2"),
                     analysis({y: 0.2 for y in range(2015, 2025)}, units="m3 m-3"))
    assert not p["numerically_comparable"] and p["mean_difference"] is None and p["annual_differences"] is None
    assert "shown separately" in p["not_comparable_reason"]
    assert p["root_mean_square_difference"] is None and p["slope_difference"] is None
    assert all(m["value"] is None for m in p["metrics"] if m["id"] in {"mean_difference", "mae", "rmse", "slope_difference"})
    assert "different physical quantities" in next(m for m in p["metrics"] if m["id"] == "rmse")["unavailable_reason"]


def test_matched_metadata_distinguishes_each_dataset_valid_years_from_pair_overlap() -> None:
    a = analysis({2018: 1.0, 2019: 2.0, 2020: 3.0, 2021: None})
    b = analysis({2017: 8.0, 2018: 2.0, 2019: 4.0, 2020: None})

    p = compare_pair(find("temperature", "nasa_power_t2m"), T_ERA5, a, b)

    assert p["matched_observations"]["labels"] == ["2018", "2019"]
    assert p["matched_observations"]["count"] == 2
    assert p["matched_observations"]["valid_observations"]["nasa_power_t2m"] == ["2018", "2019", "2020"]
    assert p["matched_observations"]["valid_observations"]["era5_land_t2m"] == ["2017", "2018", "2019"]
    assert p["matched_observations"]["excluded_from_pairing"]["nasa_power_t2m"] == ["2020"]
    assert p["matched_observations"]["excluded_from_pairing"]["era5_land_t2m"] == ["2017"]


def test_direction_metric_uses_common_period_slopes_not_different_full_periods() -> None:
    a = analysis({2018: 1.0, 2019: 2.0, 2020: 3.0, 2021: 100.0}, slope=-0.5)
    b = analysis({2017: 0.0, 2018: 1.5, 2019: 2.5, 2020: 3.5}, slope=0.5)

    p = compare_pair(find("temperature", "nasa_power_t2m"), T_ERA5, a, b)
    metric = next(m for m in p["metrics"] if m["id"] == "trend_direction")

    assert p["slope_sign_agreement"] is False  # legacy full-request context remains unchanged
    assert p["common_period_slope_sign_agreement"] is True
    assert metric["value"] is True
    assert "common eligible years" in metric["definition"]


def test_every_unavailable_metric_explains_no_common_eligible_years() -> None:
    a = analysis({2018: 1.0}, eligible={2018})
    b = analysis({2019: 2.0}, eligible={2019})

    p = compare_pair(find("temperature", "nasa_power_t2m"), T_ERA5, a, b)

    unavailable = [m for m in p["metrics"] if m["value"] is None]
    assert unavailable
    assert all(m["unavailable_reason"] for m in unavailable)
    for metric_id in {"mean_difference", "mae", "rmse"}:
        assert "No common eligible years" in next(m for m in unavailable if m["id"] == metric_id)["unavailable_reason"]


def test_constant_matched_observations_explain_undefined_correlation() -> None:
    years = range(2010, 2018)
    p = compare_pair(
        find("temperature", "nasa_power_t2m"), T_ERA5,
        analysis({year: 1.0 for year in years}), analysis({year: float(year) for year in years}),
    )

    for metric_id in ("pearson_r", "spearman_rho"):
        reason = next(m for m in p["metrics"] if m["id"] == metric_id)["unavailable_reason"]
        assert "constant" in reason.lower()


def test_agreement_levels() -> None:
    assert agreement_summary([])["level"] == "not_assessable"
    assert agreement_summary([{"slope_sign_agreement": True, "spearman_rho": 0.9}])["level"] == "consistent"
    weak = agreement_summary([{"slope_sign_agreement": True, "spearman_rho": 0.49}])
    assert weak["level"] == "same_direction_weak_covariation" and "agree" in weak["explanation"]
    assert agreement_summary([{"slope_sign_agreement": False, "spearman_rho": 0.9}])["level"] == "conflicting_trend_direction"
    assert agreement_summary([{"slope_sign_agreement": True, "spearman_rho": 0.9},
                              {"slope_sign_agreement": False, "spearman_rho": 0.3}])["level"] == "mixed"
    assert "does not prove accuracy" in agreement_summary([])["caution"]


def test_compare_reports_common_years_and_never_merges() -> None:
    a = analysis({y: 1.0 + y for y in range(2010, 2020)})
    b = analysis({y: 2.0 + y for y in range(2012, 2020)})
    out = compare([(find("temperature", "nasa_power_t2m"), a), (T_ERA5, b)])
    assert out["common_eligible_years_all"] == list(range(2012, 2020))
    assert out["all_numerically_comparable"] is True
    assert "merged" not in str(out).lower() or "never merged" in str(out).lower()
