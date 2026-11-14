import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import theilslopes

from app.api.methods_lab import METHODS, build_methods_lab
from app.api.routes import unified
from app.statistics.ols import ols_line
from app.statistics.seasonal import deseasonalized_ols_slope


FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))


# --- OLS ----------------------------------------------------------------------


def test_ols_exact_line() -> None:
    years = [2015, 2016, 2017, 2018]
    r = ols_line(years, [2 * y + 1 for y in years])
    assert r.available and r.slope == pytest.approx(2.0) and r.intercept == pytest.approx(1.0)
    assert r.r_squared == pytest.approx(1.0)
    assert all(abs(res) < 1e-9 for _, res in r.residuals)


def test_ols_matches_independent_polyfit_and_uses_calendar_years_with_gaps() -> None:
    years = [2015, 2016, 2019, 2020, 2024]
    values = [27.1, 27.4, 27.2, 27.9, 28.3]
    r = ols_line(years, values)
    slope, intercept = np.polyfit(years, values, 1)
    assert r.slope == pytest.approx(slope, rel=1e-9) and r.intercept == pytest.approx(intercept, rel=1e-9)
    by_position = np.polyfit(range(len(values)), values, 1)[0]
    assert r.slope != pytest.approx(by_position)  # array positions would give a different (wrong) slope
    ss_res = sum(res ** 2 for _, res in r.residuals)
    ss_tot = sum((v - np.mean(values)) ** 2 for v in values)
    assert r.r_squared == pytest.approx(1 - ss_res / ss_tot)


def test_ols_constant_series_has_zero_slope_and_undefined_r_squared() -> None:
    r = ols_line([2015, 2016, 2017], [5.0, 5.0, 5.0])
    assert r.available and r.slope == 0.0 and r.r_squared is None
    assert "undefined for a constant series" in r.r_squared_unavailable_reason


def test_ols_needs_minimum_observations() -> None:
    r = ols_line([2015, 2016], [1.0, 2.0])
    assert not r.available and r.slope is None and "At least 3" in r.unavailable_reason


@pytest.mark.parametrize("years, values", [([2015, 2016, 2017], [1.0, float("nan"), 2.0]), ([2015, 2015, 2017], [1.0, 2.0, 3.0])])
def test_ols_rejects_non_finite_values_and_duplicate_years(years, values) -> None:
    with pytest.raises(ValueError):
        ols_line(years, values)


def test_outlier_moves_ols_more_than_theil_sen() -> None:
    years = list(range(2010, 2020))
    clean = [10 + 0.2 * (y - 2010) for y in years]
    dirty = clean[:-1] + [clean[-1] + 10]
    ols_change = ols_line(years, dirty).slope - ols_line(years, clean).slope
    ts_change = theilslopes(dirty, years, method="separate").slope - theilslopes(clean, years, method="separate").slope
    assert abs(ols_change) > 5 * abs(ts_change)


# --- annual lab block -------------------------------------------------------------


def annual(values: dict[int, float | None], eligible: set[int]) -> list[dict]:
    return [{"year": y, "value": v, "eligible": y in eligible, "reasons": [] if y in eligible else ["insufficient_represented_months"]}
            for y, v in sorted(values.items())]


def trend(years, slope, intercept, units="°C/year", ci=(0.1, 0.3)):
    return {"eligible_years": years, "slope": slope, "intercept": intercept, "slope_units": units,
            "confidence_interval": list(ci) if ci else None, "confidence_interval_unavailable_reason": None if ci else "n/a",
            "mann_kendall": {"s": 9, "p_value": 0.02}, "serial_dependence": {"status": "not_detected_with_caveat"},
            "change_point": {"status": "none"}, "significance_unavailable_reason": None}


def test_annual_lab_uses_only_eligible_observations() -> None:
    values = {2015: 20.0, 2016: 20.5, 2017: 99.0, 2018: 21.0, 2019: 21.4}
    eligible = [2015, 2016, 2018, 2019]
    lab = build_methods_lab("temperature", annual(values, set(eligible)), trend(eligible, 0.35, -685.0))
    assert lab["applicable"] == {"annual_comparison": True, "seasonal": False}
    assert [e["year"] for e in lab["observations"]["eligible"]] == eligible
    assert lab["observations"]["excluded"] == [{"year": 2017, "value": 99.0, "reasons": ["insufficient_represented_months"]}]
    expected = np.polyfit(eligible, [values[y] for y in eligible], 1)[0]
    assert lab["ols"]["slope"] == pytest.approx(expected)
    assert lab["ols"]["slope_units"] == "°C/year" and lab["ols"]["inference"] is None
    assert lab["theil_sen"]["slope"] == 0.35 and lab["theil_sen"]["confidence_interval"] == [0.1, 0.3]
    cmp = lab["comparison"]
    assert cmp["same_observations"] and cmp["n"] == 4
    assert cmp["slope_difference"] == pytest.approx(expected - 0.35)
    assert [f["year"] for f in cmp["fitted"]] == eligible and cmp["fit_range"] == [2015, 2019]
    assert cmp["fitted"][0]["theil_sen"] == pytest.approx(-685.0 + 0.35 * 2015)


def test_annual_lab_reports_unavailable_comparison_with_reason() -> None:
    lab = build_methods_lab("temperature", annual({2015: 1.0, 2016: 2.0}, {2015, 2016}),
                            {**trend([2015, 2016], None, None), "slope_unavailable_reason": "At least 3 eligible annual observations are required"})
    assert lab["comparison"] is None
    assert "At least 3" in lab["comparison_unavailable_reason"]
    assert lab["ols"]["available"] is False and lab["theil_sen"]["available"] is False


def test_annual_lab_refuses_mismatched_observation_sets() -> None:
    lab = build_methods_lab("temperature", annual({2015: 1.0, 2016: None, 2017: 3.0}, {2015, 2016, 2017}),
                            trend([2015, 2016, 2017], 1.0, 0.0))
    assert "could not be matched" in lab["unavailable"] and "comparison" not in lab


def test_annual_lab_carries_existing_results_unchanged() -> None:
    t = trend([2015, 2016, 2017], 1.0, 0.0)
    lab = build_methods_lab("precipitation", annual({2015: 1.0, 2016: 2.0, 2017: 3.0}, {2015, 2016, 2017}), t)
    assert lab["mann_kendall"] is t["mann_kendall"] and lab["serial_dependence"] is t["serial_dependence"]
    assert lab["change_point"] is t["change_point"]
    assert lab["requirements"]["minimum_years_for_significance"] == 8 and lab["requirements"]["alpha"] == 0.05
    assert set(METHODS) >= {"ols", "theil_sen", "mann_kendall", "serial_dependence", "seasonal_kendall", "change_point"}
    assert lab["seasonal"] is None and lab["seasonal_unavailable_reason"]


# --- seasonal lab block -------------------------------------------------------------


def test_seasonal_lab_uses_the_same_monthly_sample() -> None:
    monthly = {(y, m): 0.4 + 0.01 * (y - 2015) + 0.05 * m for y in range(2015, 2025) for m in (1, 2, 3, 11, 12)}
    monthly[(2016, 7)] = 0.9  # month 7 is not in months_used and must be ignored
    t = {"method": "seasonal_kendall", "months_used": [1, 2, 3, 11, 12], "eligible_years": list(range(2015, 2025)),
         "sample_count": 50, "slope": 0.01, "slope_units": "NDVI units/year", "confidence_interval": [0.008, 0.012],
         "confidence_interval_unavailable_reason": None, "mann_kendall": {"s": 200}, "serial_dependence": None, "change_point": {"status": "none"}}
    lab = build_methods_lab("ndvi", [], t, monthly)
    assert lab["applicable"] == {"annual_comparison": False, "seasonal": True}
    assert "different sample" in lab["annual_comparison_unavailable_reason"]
    s = lab["seasonal"]
    assert s["months_not_used"] == [4, 5, 6, 7, 8, 9, 10]
    assert s["month_names_used"] == ["Jan", "Feb", "Mar", "Nov", "Dec"]
    same = {k: v for k, v in monthly.items() if k[1] in t["months_used"]}
    assert s["deseasonalized_ols_slope"] == pytest.approx(deseasonalized_ols_slope(same, t["months_used"]))
    # The existing helper pools months against decimal year without centring x per month, which slightly
    # attenuates the slope on perfectly linear data (disclosed in comparison_note); it is reused unchanged.
    assert s["deseasonalized_ols_slope"] == pytest.approx(0.01, rel=0.03)
    assert s["deseasonalized_ols_slope"] < 0.01
    assert s["seasonal_sen_slope"] == 0.01 and s["confidence_interval"] == [0.008, 0.012]
    assert "not identical estimators" in s["comparison_note"]


def test_seasonal_lab_without_months_reports_unavailable() -> None:
    t = {"method": "seasonal_kendall", "months_used": [], "eligible_years": [], "slope": None, "slope_units": None}
    s = build_methods_lab("ndvi", [], t, {})["seasonal"]
    assert s["deseasonalized_ols_slope"] is None and s["deseasonalized_ols_unavailable_reason"]


# --- API compatibility with real (stored live) responses --------------------------------


@pytest.mark.parametrize("variable, key", [("temperature", "temperature_trend"), ("relative_humidity", "rh_trend"),
                                           ("precipitation", "precip_trend"), ("extreme_heat", "heat_trend")])
def test_normalise_adds_methods_lab_without_changing_existing_fields(variable, key) -> None:
    body = FIXTURE[key]
    out = unified.normalise(variable, body, 16.8661, 96.1951)
    for field in ("variable", "dataset", "spatial_support", "annual", "series", "trend", "coverage", "methodology", "caveats", "limitations"):
        assert field in out
    lab = out["methods_lab"]
    assert lab["theil_sen"]["slope"] == out["trend"]["slope"]
    eligible = [a for a in out["annual"] if a["eligible"]]
    years = [a["year"] for a in eligible]
    assert [e["year"] for e in lab["observations"]["eligible"]] == sorted(out["trend"]["eligible_years"]) == years
    assert lab["ols"]["slope"] == pytest.approx(np.polyfit(years, [a["value"] for a in eligible], 1)[0], rel=1e-9)
    json.dumps(lab, allow_nan=False)  # finite, serialisable


def test_normalise_ndvi_returns_seasonal_lab_from_live_fixture() -> None:
    out = unified.normalise("ndvi", FIXTURE["ndvi_trend"], 16.8661, 96.1951)
    lab = out["methods_lab"]
    assert lab["applicable"]["seasonal"] is True and lab["comparison"] if "comparison" in lab else True
    assert lab["seasonal"]["months_used"] == out["trend"]["months_used"]
    assert lab["seasonal"]["seasonal_sen_slope"] == out["trend"]["slope"]


def test_mann_kendall_tau_definition_matches_the_backend_calculation() -> None:
    from math import sqrt

    from app.statistics.trend import _mann_kendall

    d = METHODS["mann_kendall"]["definition"]
    assert "√(n₀(n₀ − n₁))" in d and "tie-adjusted" in d and "S / number of pairs" not in d
    # Verify the documented formula against the unchanged engine on a series with tied values.
    values = [1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 5.0, 4.0, 6.0]
    mk = _mann_kendall(values, 0.05)
    assert mk is not None
    n = len(values)
    s = sum((values[j] > values[i]) - (values[j] < values[i]) for i in range(n) for j in range(i + 1, n))
    n0 = n * (n - 1) / 2
    n1 = sum(c * (c - 1) / 2 for c in (values.count(v) for v in set(values)))
    assert mk.tau == pytest.approx(s / sqrt(n0 * (n0 - n1)))
    assert mk.tau != pytest.approx(s / n0)
    assert "no tie adjustment" in METHODS["seasonal_kendall"]["definition"]


def test_deseasonalized_note_does_not_present_the_fixture_gap_as_a_general_bias() -> None:
    monthly = {(y, m): 0.4 + 0.01 * (y - 2015) + 0.05 * m for y in range(2015, 2025) for m in (1, 2, 3, 11, 12)}
    t = {"method": "seasonal_kendall", "months_used": [1, 2, 3, 11, 12], "eligible_years": list(range(2015, 2025)),
         "sample_count": 50, "slope": 0.01, "slope_units": "NDVI units/year", "confidence_interval": None,
         "confidence_interval_unavailable_reason": "n/a", "mann_kendall": None, "serial_dependence": None, "change_point": None}
    note = build_methods_lab("ndvi", [], t, monthly)["seasonal"]["comparison_note"]
    assert "synthetic unit-test fixture" in note
    assert "not an expected bias" in note and "must not be used as a correction" in note
    assert "perfectly linear test data" not in note
