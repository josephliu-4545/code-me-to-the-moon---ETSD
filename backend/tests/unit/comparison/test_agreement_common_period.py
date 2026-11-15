"""Headline dataset agreement must rest on matched (common-period) evidence and be worded as
descriptive unless the datasets' own tests apply to exactly those years.

Phase 2 scientific presentation corrections. Estimators are unchanged: common-period slopes are the
existing Theil–Sen slopes over common eligible years, verified here against SciPy directly.
"""

import json
from pathlib import Path

import pytest
from scipy.stats import theilslopes

from app.api.routes import unified
from app.comparison.catalog import find
from app.comparison.engine import agreement_summary, compare, compare_pair

POWER = find("temperature", "nasa_power_t2m")
ERA5 = find("temperature", "era5_land_t2m")
GLDAS_T = find("temperature", "gldas_2_1_tair")
IMERG = find("precipitation", "gpm_imerg_v07")
ERA5_P = find("precipitation", "era5_land_tp")
GLDAS_SM = find("soil_moisture", "gldas_2_1_noah_0_10cm")
SMAP = find("soil_moisture", "smap_l3e_v006_am")


def analysis(values: dict[int, float | None], units="°C", slope=0.1, significant=None, level="descriptive_slope"):
    eligible = {y for y, v in values.items() if v is not None}
    mk = None if significant is None else {"is_statistically_significant": significant, "p_value": 0.01 if significant else 0.6}
    return {
        "units": {"annual_value": units},
        "annual": [{"year": y, "value": v, "eligible": y in eligible} for y, v in sorted(values.items())],
        "trend": {"slope": slope, "confidence_interval": None, "result_level": level, "mann_kendall": mk},
    }


def years(a: int, b: int) -> range:
    return range(a, b + 1)


# --- pair-level direction evidence -----------------------------------------------------------


def test_common_period_slopes_match_scipy_on_the_common_years() -> None:
    a_vals = {y: 20 + 0.03 * (y - 2010) + (0.4 if y % 3 == 0 else 0.0) for y in years(2010, 2021)}
    b_vals = {y: 19 + 0.05 * (y - 2010) - (0.3 if y % 4 == 0 else 0.0) for y in years(2013, 2024)}
    p = compare_pair(POWER, ERA5, analysis(a_vals), analysis(b_vals))
    common = list(years(2013, 2021))
    assert p["common_eligible_years"] == common
    assert p["common_period_slopes"]["nasa_power_t2m"] == pytest.approx(theilslopes([a_vals[y] for y in common], common, method="separate").slope)
    assert p["common_period_slopes"]["era5_land_t2m"] == pytest.approx(theilslopes([b_vals[y] for y in common], common, method="separate").slope)


def test_descriptive_same_and_opposite_directions_are_labelled_descriptive() -> None:
    up = {y: float(y) for y in years(2015, 2024)}
    down = {y: -float(y) for y in years(2015, 2024)}
    same = compare_pair(POWER, ERA5, analysis(up), analysis(up))
    opposite = compare_pair(POWER, ERA5, analysis(up), analysis(down))
    assert same["direction_evidence"] == "descriptive_same_direction"
    assert opposite["direction_evidence"] == "descriptive_opposite_direction"


def test_fewer_than_three_common_years_makes_direction_unavailable_even_if_full_slopes_agree() -> None:
    a = analysis({2015: 1.0, 2016: 2.0, 2017: 3.0, 2018: 4.0}, slope=1.0)
    b = analysis({2017: 1.0, 2018: 2.0, 2019: 3.0, 2020: 4.0}, slope=1.0)
    p = compare_pair(POWER, ERA5, a, b)
    assert p["common_eligible_years"] == [2017, 2018]
    assert p["slope_sign_agreement"] is True  # legacy full-request field still reported
    assert p["common_period_slope_sign_agreement"] is None
    assert p["direction_evidence"] == "unavailable"


def test_no_overlap_makes_direction_unavailable() -> None:
    p = compare_pair(POWER, ERA5, analysis({y: float(y) for y in years(2001, 2005)}), analysis({y: float(y) for y in years(2010, 2014)}))
    assert p["common_eligible_years"] == [] and p["direction_evidence"] == "unavailable"


def test_indicative_only_when_both_tests_apply_to_exactly_the_common_years() -> None:
    up = {y: float(y) + (0.1 if y % 2 else 0) for y in years(2015, 2024)}
    full = compare_pair(POWER, ERA5, analysis(up, significant=True, level="statistical_inference"),
                        analysis(up, significant=True, level="statistical_inference"))
    assert full["direction_evidence"] == "indicative_same_direction"
    # Same significant results, but B has extra eligible years: its test used a different sample.
    longer = dict(up) | {2012: 2012.0, 2013: 2013.0, 2014: 2014.0}
    partial = compare_pair(POWER, ERA5, analysis(up, significant=True, level="statistical_inference"),
                           analysis(longer, significant=True, level="statistical_inference"))
    assert partial["direction_evidence"] == "descriptive_same_direction"
    # One non-significant test: descriptive.
    weak = compare_pair(POWER, ERA5, analysis(up, significant=True, level="statistical_inference"),
                        analysis(up, significant=False, level="statistical_inference"))
    assert weak["direction_evidence"] == "descriptive_same_direction"


def test_near_zero_opposite_slopes_are_not_an_established_conflict() -> None:
    flat_up = {y: 10.0 + (0.001 * (y - 2015)) + (0.5 if y % 2 else -0.5) for y in years(2015, 2024)}
    flat_down = {y: 10.0 - (0.001 * (y - 2015)) + (0.5 if y % 2 else -0.5) for y in years(2015, 2024)}
    p = compare_pair(POWER, ERA5, analysis(flat_up, significant=False, level="statistical_inference"),
                     analysis(flat_down, significant=False, level="statistical_inference"))
    assert p["direction_evidence"] == "descriptive_opposite_direction"
    summary = agreement_summary([p])
    assert summary["direction_evidence"] == "descriptive"
    assert "not an established" in summary["explanation"]
    assert "disagree on the direction" not in summary["explanation"]


def test_different_quantities_compare_direction_only() -> None:
    p = compare_pair(GLDAS_SM, SMAP, analysis({y: 20.0 + y * 0.1 for y in years(2015, 2024)}, units="kg m-2"),
                     analysis({y: 0.2 + y * 0.001 for y in years(2015, 2024)}, units="m3 m-3"))
    assert not p["numerically_comparable"] and p["slope_difference"] is None
    assert p["direction_evidence"] == "descriptive_same_direction"
    assert "direction only" in agreement_summary([p])["comparability_note"]


def test_full_period_confidence_intervals_are_never_attached_to_common_slopes() -> None:
    a = analysis({y: float(y) for y in years(2010, 2024)})
    a["trend"]["confidence_interval"] = [0.9, 1.1]
    p = compare_pair(POWER, ERA5, a, analysis({y: float(y) for y in years(2015, 2024)}))
    assert not any("interval" in k and "common" in k for k in p)


# --- headline summary ------------------------------------------------------------------------


def test_headline_uses_common_period_not_full_period_signs() -> None:
    # Full-request slopes point opposite ways (different samples); over common years both rise.
    a = analysis({2018: 1.0, 2019: 2.0, 2020: 3.0, 2021: 100.0}, slope=-0.5)
    b = analysis({2017: 0.0, 2018: 1.5, 2019: 2.5, 2020: 3.5}, slope=0.5)
    summary = compare([(POWER, a), (ERA5, b)])["agreement"]
    assert summary["level"] != "conflicting_trend_direction"
    assert summary["slope_sign_agreement_all"] is True
    assert summary["basis"] == "common_period_descriptive_slopes"


def test_same_direction_without_correlation_is_not_called_weak_covariation() -> None:
    p = compare_pair(POWER, ERA5, analysis({y: float(y) for y in years(2015, 2019)}), analysis({y: 2.0 * y for y in years(2015, 2019)}))
    summary = agreement_summary([p])
    assert summary["level"] == "same_direction_covariation_not_assessable"
    assert "weak" not in summary["explanation"].lower()


def test_insufficient_overlap_is_not_assessable_never_consistent() -> None:
    a = analysis({2015: 1.0, 2016: 2.0, 2017: 3.0}, slope=1.0)
    b = analysis({2017: 1.0, 2018: 2.0, 2019: 3.0}, slope=1.0)
    summary = compare([(POWER, a), (ERA5, b)])["agreement"]
    assert summary["level"] == "not_assessable" and summary["slope_sign_agreement_all"] is None


def test_every_level_has_cautious_label_and_descriptive_wording() -> None:
    up = {y: float(y) + (0.3 if y % 2 else 0) for y in years(2010, 2024)}
    down = {y: -float(y) + (0.3 if y % 2 else 0) for y in years(2010, 2024)}
    cases = [
        [],
        [compare_pair(POWER, ERA5, analysis(up), analysis(up))],
        [compare_pair(POWER, ERA5, analysis(up), analysis(down))],
        [compare_pair(POWER, ERA5, analysis(up), analysis(up)), compare_pair(POWER, GLDAS_T, analysis(up), analysis(down))],
    ]
    for pairs in cases:
        s = agreement_summary(pairs)
        assert s["label"] and s["explanation"] and s["caution"]
        assert "does not prove accuracy" in s["caution"]
        text = (s["label"] + " " + s["explanation"]).lower()
        assert "proven" not in text and "confirmed" not in text
        if s["level"] == "conflicting_trend_direction":
            assert "opposite" in s["label"].lower() and "conflict" not in s["label"].lower()


def test_shared_inputs_are_flagged_in_the_summary() -> None:
    up = {y: float(y) for y in years(2010, 2024)}
    related = agreement_summary([compare_pair(POWER, ERA5, analysis(up), analysis(up))])
    assert "not independent" in related["independence_note"]
    independent = agreement_summary([compare_pair(IMERG, ERA5_P, analysis(up, units="mm"), analysis(up, units="mm"))])
    assert independent["independence_note"] is None or "not independent" not in independent["independence_note"]


def test_existing_identifiers_and_fields_remain_for_api_consumers() -> None:
    s = agreement_summary([])
    assert set(s) >= {"level", "slope_sign_agreement_all", "min_spearman_rho", "explanation", "caution"}


# --- NDVI seasonal estimator unchanged -----------------------------------------------------------


def test_ndvi_seasonal_estimates_are_unchanged_on_the_live_yangon_fixture() -> None:
    """Baseline from main 0d10550 on the stored live Yangon 2015–2025 response; this branch changes presentation only."""
    fixture = json.loads((Path(__file__).parents[2] / "fixtures" / "v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))
    trend = unified.normalise("ndvi", fixture["ndvi_trend"], 16.8661, 96.1951)["trend"]
    assert trend["method"] == "seasonal_kendall" and trend["months_used"] == [1, 2, 3, 4, 11, 12]
    assert trend["sample_count"] == 60
    assert trend["slope"] == pytest.approx(0.00634673064201699, rel=1e-12)
    assert trend["intercept"] == pytest.approx(-12.310495941224127, rel=1e-12)
    assert trend["confidence_interval"] == pytest.approx([0.004107251696861269, 0.00823779457354302], rel=1e-12)
    assert trend["mann_kendall"]["s"] == 118 and trend["mann_kendall"]["variance"] == pytest.approx(750.0)
    assert trend["mann_kendall"]["p_value"] == pytest.approx(1.935226468430251e-05, rel=1e-9)
