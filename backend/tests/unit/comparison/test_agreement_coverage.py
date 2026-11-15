"""The headline must not generalise from a subset of dataset pairs.

PR #9 review: directions unavailable for some pairs, or correlations available for a different
subset of pairs, must not produce an "all pairs" headline. Estimators are unchanged.
"""

from app.comparison.catalog import find
from app.comparison.engine import agreement_summary, compare, compare_pair

POWER = find("temperature", "nasa_power_t2m")
GLDAS_T = find("temperature", "gldas_2_1_tair")
ERA5 = find("temperature", "era5_land_t2m")
IMERG = find("precipitation", "gpm_imerg_v07")
CHIRPS = find("precipitation", "chirps_v2_daily")
ERA5_P = find("precipitation", "era5_land_tp")
NAMES = {e.key: e.name for e in (POWER, GLDAS_T, ERA5, IMERG, CHIRPS, ERA5_P)}


def analysis(values: dict[int, float], units="°C"):
    return {
        "units": {"annual_value": units},
        "annual": [{"year": y, "value": v, "eligible": True} for y, v in sorted(values.items())],
        "trend": {"slope": 0.1, "confidence_interval": None, "result_level": "descriptive_slope", "mann_kendall": None},
    }


def rising(first: int, last: int, offset: float = 0.0, wiggle: float = 0.3):
    return {y: offset + 0.1 * (y - first) + (wiggle if y % 2 else 0.0) for y in range(first, last + 1)}


def falling(first: int, last: int, offset: float = 0.0, wiggle: float = 0.3):
    return {y: offset - 0.1 * (y - first) + (wiggle if y % 2 else 0.0) for y in range(first, last + 1)}


# --- three datasets: only one pair assessable ------------------------------------------------


def test_one_of_three_pairs_assessed_is_partial_not_consistent() -> None:
    # A and B overlap 2010-2019; C only shares 2 years with each, so those directions are unavailable.
    a, b, c = analysis(rising(2010, 2019)), analysis(rising(2010, 2019, 1.0)), analysis(rising(2018, 2024, 2.0))
    s = compare([(POWER, a), (ERA5, b), (GLDAS_T, c)])["agreement"]
    assert s["direction_coverage"] == "partial"
    assert s["pairs_with_direction"] == 1 and s["pairs_without_direction"] == 2
    assert s["level"] == "partially_assessable"
    assert s["level"] not in {"consistent", "same_direction_weak_covariation", "conflicting_trend_direction", "mixed"}
    assert s["slope_sign_agreement_all"] is None  # never an "all pairs" claim from a subset
    assert "1 of 3" in s["label"] and "every pair" not in s["explanation"]
    assert "No overall conclusion" in s["explanation"]


def test_partial_coverage_keeps_each_available_pairwise_finding() -> None:
    a, b, c = analysis(rising(2010, 2019)), analysis(falling(2010, 2019, 1.0)), analysis(rising(2018, 2024, 2.0))
    s = compare([(POWER, a), (ERA5, b), (GLDAS_T, c)])["agreement"]
    findings = {tuple(f["datasets"]): f for f in s["pair_findings"]}
    assert len(findings) == 3
    assert findings[("nasa_power_t2m", "era5_land_t2m")]["direction_evidence"] == "descriptive_opposite_direction"
    assert findings[("nasa_power_t2m", "gldas_2_1_tair")]["direction_evidence"] == "unavailable"
    assert "NASA POWER" in s["explanation"] and "ERA5-Land" in s["explanation"]
    assert "opposite" in s["explanation"]


# --- four datasets: mixed availability ------------------------------------------------------


def test_four_datasets_with_half_the_pairs_assessed_do_not_get_a_mixed_or_conflict_headline() -> None:
    # Precipitation-style example: A, B, C overlap fully (3 pairs); D shares 2 years with everyone (3 pairs).
    a, b = analysis(rising(2010, 2019), "mm"), analysis(falling(2010, 2019, 5.0), "mm")
    c, d = analysis(falling(2010, 2019, 9.0), "mm"), analysis(rising(2018, 2024, 3.0), "mm")
    extra = find("precipitation", "chirps_v2_daily")
    pairs = [compare_pair(x, y, rx, ry) for (x, rx), (y, ry) in
             [((IMERG, a), (ERA5_P, b)), ((IMERG, a), (CHIRPS, c)), ((ERA5_P, b), (CHIRPS, c)),
              ((IMERG, a), (extra, d)), ((ERA5_P, b), (extra, d)), ((CHIRPS, c), (extra, d))]]
    s = agreement_summary(pairs, NAMES)
    assert s["direction_coverage"] == "partial" and s["pairs_with_direction"] == 3
    assert s["level"] == "partially_assessable"
    assert "3 of 6" in s["label"]


def test_no_pairs_assessed() -> None:
    a, b, c = analysis(rising(2001, 2004)), analysis(rising(2004, 2007)), analysis(rising(2010, 2014))
    s = compare([(POWER, a), (ERA5, b), (GLDAS_T, c)])["agreement"]
    assert s["direction_coverage"] == "none" and s["level"] == "not_assessable"
    assert s["slope_sign_agreement_all"] is None


# --- complete directions, incomplete correlations ----------------------------------------------


def test_correlation_from_one_pair_does_not_make_an_all_pairs_covariation_headline() -> None:
    # All three pairs have >= 3 common years (directions complete), but only A-B has >= 8 for correlation.
    a, b, c = analysis(rising(2010, 2019)), analysis(rising(2010, 2019, 1.0)), analysis(rising(2014, 2018, 2.0))
    s = compare([(POWER, a), (ERA5, b), (GLDAS_T, c)])["agreement"]
    assert s["direction_coverage"] == "complete"
    assert s["covariation_coverage"] == "partial"
    assert s["level"] == "same_direction_covariation_not_assessable"
    assert s["level"] not in {"consistent", "same_direction_weak_covariation"}
    assert "1 of 3" in s["explanation"]
    assert "NASA POWER 2 m air temperature (T2M) vs ERA5-Land monthly 2 m air temperature" in s["explanation"]


def test_complete_directions_and_correlations_name_the_weakest_pair() -> None:
    a, b, c = analysis(rising(2010, 2019)), analysis(rising(2010, 2019, 1.0)), analysis(rising(2010, 2019, 2.0, wiggle=-0.3))
    s = compare([(POWER, a), (ERA5, b), (GLDAS_T, c)])["agreement"]
    assert s["direction_coverage"] == "complete" and s["covariation_coverage"] == "complete"
    assert s["level"] in {"consistent", "same_direction_weak_covariation"}
    assert "lowest" in s["explanation"] and " vs " in s["explanation"]


def test_complete_coverage_single_pair_keeps_existing_levels() -> None:
    s = compare([(POWER, analysis(rising(2010, 2019))), (ERA5, analysis(falling(2010, 2019)))])["agreement"]
    assert s["direction_coverage"] == "complete" and s["level"] == "conflicting_trend_direction"
    assert s["slope_sign_agreement_all"] is False
