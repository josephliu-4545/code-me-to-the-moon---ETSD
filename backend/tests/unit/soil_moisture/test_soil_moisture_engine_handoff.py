from datetime import date
import inspect

import pytest

from app.soil_moisture.aggregation import (
    analyze_series,
    annual_policy,
    assess_months,
    to_observation_series,
)
from app.soil_moisture.datasets import DepthSemantics, ProductType, get_dataset
from app.soil_moisture.models import (
    CatalogAvailability,
    MonthlySample,
    MonthlySoilMoistureSeries,
    SupportPolicy,
    expected_slots,
)
from app.statistics.annual import aggregate_annual
from app.statistics.models import ObservationSeries
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend
from app.soil_moisture.units import QuantityKind


GLDAS = get_dataset("gldas_2_1_noah_0_10cm")
SMAP5 = get_dataset("smap_l3e_v005_am")
SMAP6 = get_dataset("smap_l3e_v006_am")
GLDAS_AVAIL = CatalogAvailability("NASA/GLDAS/V021/NOAH/G025/T3H", date(2000, 1, 1), date(2026, 10, 15))
SMAP5_AVAIL = CatalogAvailability("NASA/SMAP/SPL3SMP_E/005", date(2015, 3, 31), date(2023, 12, 3))
SMAP6_AVAIL = CatalogAvailability("NASA/SMAP/SPL3SMP_E/006", date(2023, 12, 4), date(2026, 11, 10))
POLICY = SupportPolicy()
TREND = TrendPolicy()
SPREAD_DAYS = [2, 5, 8, 12, 15, 18, 22, 25, 28]

# Year noise chosen so Theil-Sen recovers exactly 0.5 and lag-1 residual
# dependence is negligible (rho ~ -0.02), letting Mann-Kendall run.
GOLDEN_NOISE = [0.04, 0.08, 0.08, 0.11, -0.01, -0.3, 0.18, 0.15, 0.0, 0.02]


def months(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def gldas_series(start: date, end: date, value=lambda m: 24.0, skip=(), weak=(),
                 policy=POLICY, avail=GLDAS_AVAIL) -> MonthlySoilMoistureSeries:
    samples = []
    for m in months(start, end):
        if m in skip:
            continue
        slots = expected_slots(GLDAS, m)
        valid = 10 if m in weak else slots
        samples.append(MonthlySample(m, slots, valid, value(m)))
    return assess_months(GLDAS, tuple(samples), avail, start, end, policy)


def smap_series(descriptor, avail, start: date, end: date, value=lambda m: 0.25):
    samples = []
    for m in months(start, end):
        if not avail.first_image_date.replace(day=1) <= m <= avail.last_image_date:
            continue
        days = [d for d in SPREAD_DAYS
                if avail.first_image_date <= m.replace(day=d) <= avail.last_image_date]
        dates = tuple(m.replace(day=d) for d in days)
        samples.append(MonthlySample(m, len(dates), len(dates), value(m) if dates else None, dates))
    return assess_months(descriptor, tuple(samples), avail, start, end, POLICY)


# --- handoff to ObservationSeries ---------------------------------------------


def test_complete_year_maps_to_twelve_monthly_observations() -> None:
    obs = to_observation_series(gldas_series(date(2020, 1, 1), date(2021, 1, 1)), GLDAS)
    assert isinstance(obs, ObservationSeries)
    assert obs.variable == "soil_moisture"
    assert obs.dataset == "gldas_2_1_noah_0_10cm"
    assert obs.value_units == "kg m-2"
    assert [o.date for o in obs.observations] == months(date(2020, 1, 1), date(2021, 1, 1))
    (coverage,) = obs.coverage_by_year
    assert coverage.year == 2020
    assert len(coverage.expected_slot_dates) == 12
    assert len(coverage.available_image_dates) == 12
    assert coverage.is_complete_calendar_year
    for o in obs.observations:
        assert o.valid_pixel_count is None and o.spatial_coverage_percentage is None


def test_only_usable_months_become_observations() -> None:
    series = gldas_series(date(2020, 1, 1), date(2021, 1, 1),
                          skip={date(2020, 3, 1)}, weak={date(2020, 7, 1)})
    obs = to_observation_series(series, GLDAS)
    dates = {o.date for o in obs.observations}
    assert date(2020, 3, 1) not in dates           # no images
    assert date(2020, 7, 1) not in dates           # insufficient support (descriptive mean exists)
    assert len(dates) == 10
    (coverage,) = obs.coverage_by_year
    assert date(2020, 3, 1) not in coverage.available_image_dates
    assert date(2020, 7, 1) in coverage.available_image_dates


def test_provisional_months_are_not_handed_to_the_engine() -> None:
    series = gldas_series(date(2026, 1, 1), date(2026, 11, 1))
    dates = {o.date for o in to_observation_series(series, GLDAS).observations}
    assert date(2026, 6, 1) in dates
    assert not dates & {date(2026, m, 1) for m in (7, 8, 9, 10)}


def test_series_must_belong_to_the_descriptor() -> None:
    v5 = smap_series(SMAP5, SMAP5_AVAIL, date(2020, 1, 1), date(2021, 1, 1))
    with pytest.raises(ValueError, match="does not belong"):
        to_observation_series(v5, SMAP6)
    with pytest.raises(ValueError, match="does not belong"):
        analyze_series(v5, SMAP6, TREND)


def test_derived_volumetric_series_only_for_storage_datasets() -> None:
    v5 = smap_series(SMAP5, SMAP5_AVAIL, date(2020, 1, 1), date(2021, 1, 1))
    with pytest.raises(ValueError, match="derived volumetric"):
        to_observation_series(v5, SMAP5, derived_volumetric=True)


def test_derived_volumetric_series_divides_storage_by_one_hundred() -> None:
    series = gldas_series(date(2020, 1, 1), date(2021, 1, 1), value=lambda m: 20.0 + m.month)
    native = to_observation_series(series, GLDAS)
    derived = to_observation_series(series, GLDAS, derived_volumetric=True)
    assert derived.value_units == "m3 m-3"
    for a, b in zip(native.observations, derived.observations, strict=True):
        assert b.date == a.date
        assert b.value == pytest.approx(a.value / 100, abs=1e-12)


# --- annual aggregation through the shared engine -----------------------------


def test_complete_year_is_eligible_with_equal_weight_monthly_mean() -> None:
    values = {m: float(m) * 2 for m in range(1, 13)}
    series = gldas_series(date(2021, 1, 1), date(2022, 1, 1), value=lambda d: values[d.month])
    (summary,) = analyze_series(series, GLDAS, TREND).annual_summaries
    assert summary.eligible_for_trend_inference
    assert summary.eligibility_reasons == ()
    # Equal-weight mean of 12 monthly means, not weighted by days in month.
    assert summary.annual_value == pytest.approx(sum(values.values()) / 12)
    assert summary.value_units == "kg m-2"


def test_missing_month_makes_year_ineligible_but_keeps_descriptive_value() -> None:
    series = gldas_series(date(2021, 1, 1), date(2022, 1, 1), skip={date(2021, 3, 1)})
    analysis = analyze_series(series, GLDAS, TREND)
    (summary,) = analysis.annual_summaries
    assert not summary.eligible_for_trend_inference
    assert "insufficient_represented_months" in summary.eligibility_reasons
    assert "insufficient_valid_slot_coverage" in summary.eligibility_reasons
    assert summary.annual_value == pytest.approx(24.0)  # descriptive, from 11 months
    assert summary.missing_months == (3,)
    (support,) = analysis.year_support
    assert support.missing_months == ((3, "no_images"),)


def test_insufficient_monthly_coverage_excludes_the_year() -> None:
    series = gldas_series(date(2021, 1, 1), date(2022, 1, 1), weak={date(2021, 8, 1)})
    analysis = analyze_series(series, GLDAS, TREND)
    (summary,) = analysis.annual_summaries
    assert not summary.eligible_for_trend_inference
    assert summary.missing_months == (8,)
    assert analysis.year_support[0].missing_months == ((8, "insufficient_support"),)


def test_missing_quarter_reason_is_preserved() -> None:
    skip = {date(2021, m, 1) for m in (4, 5, 6)}
    (summary,) = analyze_series(gldas_series(date(2021, 1, 1), date(2022, 1, 1), skip=skip),
                                GLDAS, TREND).annual_summaries
    assert "missing_calendar_quarter" in summary.eligibility_reasons


def test_partial_year_is_described_but_excluded() -> None:
    analysis = analyze_series(gldas_series(date(2019, 11, 1), date(2021, 1, 1)), GLDAS, TREND)
    first, second = analysis.annual_summaries
    assert first.year == 2019 and not first.is_complete_calendar_year
    assert "partial_calendar_year" in first.eligibility_reasons
    assert first.annual_value == pytest.approx(24.0)
    assert second.year == 2020 and second.eligible_for_trend_inference


def test_legitimate_zero_month_enters_the_annual_mean() -> None:
    series = gldas_series(date(2021, 1, 1), date(2022, 1, 1),
                          value=lambda m: 0.0 if m.month == 1 else 12.0)
    (summary,) = analyze_series(series, GLDAS, TREND).annual_summaries
    assert summary.eligible_for_trend_inference
    assert (1, 0.0) in summary.monthly_values
    assert summary.annual_value == pytest.approx(11 * 12.0 / 12)


def test_engine_receives_the_soil_moisture_annual_policy() -> None:
    series = gldas_series(date(2021, 1, 1), date(2022, 1, 1))
    expected = aggregate_annual(to_observation_series(series, GLDAS), annual_policy(GLDAS))
    assert analyze_series(series, GLDAS, TREND).annual_summaries == expected


# --- units, depth, provenance -------------------------------------------------


def test_gldas_analysis_reports_native_and_derived_units_separately() -> None:
    analysis = analyze_series(gldas_series(date(2021, 1, 1), date(2022, 1, 1),
                                           value=lambda m: 25.0), GLDAS, TREND)
    assert analysis.units == "kg m-2"
    assert analysis.derived_units == "m3 m-3"
    (native,) = analysis.annual_summaries
    (derived,) = analysis.derived_annual_summaries
    assert native.value_units == "kg m-2" and derived.value_units == "m3 m-3"
    assert derived.annual_value == pytest.approx(0.25, abs=1e-12)
    assert derived.eligible_for_trend_inference == native.eligible_for_trend_inference


def test_analysis_preserves_dataset_provenance_and_depth() -> None:
    gldas = analyze_series(gldas_series(date(2021, 1, 1), date(2022, 1, 1)), GLDAS, TREND)
    assert (gldas.dataset_key, gldas.collection_id, gldas.version) == (
        "gldas_2_1_noah_0_10cm", "NASA/GLDAS/V021/NOAH/G025/T3H", "2.1")
    assert gldas.product_type is ProductType.LAND_SURFACE_MODEL_OPEN_LOOP
    assert gldas.quantity_kind is QuantityKind.LAYER_WATER_STORAGE
    assert (gldas.depth_top_cm, gldas.depth_bottom_cm) == (0.0, 10.0)
    assert gldas.depth_semantics is DepthSemantics.MODEL_LAYER
    assert gldas.value_definition == "mean of 3-hourly instantaneous layer states"
    assert gldas.annual_aggregation == "equal-weight mean of monthly means"

    smap = analyze_series(smap_series(SMAP5, SMAP5_AVAIL, date(2021, 1, 1), date(2022, 1, 1)),
                          SMAP5, TREND)
    assert smap.product_type is ProductType.SATELLITE_RETRIEVAL
    assert smap.quantity_kind is QuantityKind.VOLUMETRIC_WATER_CONTENT
    assert (smap.depth_top_cm, smap.depth_bottom_cm) == (0.0, 5.0)
    assert smap.depth_semantics is DepthSemantics.APPROXIMATE_SENSING_DEPTH
    assert smap.units == "m3 m-3"
    assert smap.value_definition == "mean of valid sampled days"


def test_smap_analysis_has_no_derived_results() -> None:
    smap = analyze_series(smap_series(SMAP5, SMAP5_AVAIL, date(2021, 1, 1), date(2022, 1, 1)),
                          SMAP5, TREND)
    assert smap.derived_units is None
    assert smap.derived_annual_summaries is None
    assert smap.derived_trend is None


def test_analysis_labels_policies_as_not_universal_standards() -> None:
    analysis = analyze_series(gldas_series(date(2021, 1, 1), date(2022, 1, 1)), GLDAS, TREND)
    assert analysis.thresholds_are_universal_standards is False
    assert analysis.support_policy_status == "provisional_pending_live_validation"


# --- SMAP version separation --------------------------------------------------


def test_v005_analysis_never_contains_v006_months() -> None:
    analysis = analyze_series(
        smap_series(SMAP5, SMAP5_AVAIL, date(2023, 1, 1), date(2024, 7, 1)), SMAP5, TREND)
    obs = to_observation_series(analysis.monthly, SMAP5)
    assert obs.dataset == "smap_l3e_v005_am"
    assert max(o.date for o in obs.observations) <= date(2023, 11, 1)
    years = {s.year: s for s in analysis.annual_summaries}
    assert years[2023].eligible_for_trend_inference is False  # Dec 2023 truncated
    assert years[2024].annual_value is None                   # no V005 data at all
    assert "no_valid_observations" in years[2024].eligibility_reasons


def test_v006_analysis_starts_at_its_own_collection() -> None:
    analysis = analyze_series(
        smap_series(SMAP6, SMAP6_AVAIL, date(2023, 1, 1), date(2025, 1, 1)), SMAP6, TREND)
    obs = to_observation_series(analysis.monthly, SMAP6)
    assert obs.dataset == "smap_l3e_v006_am"
    assert min(o.date for o in obs.observations) == date(2023, 12, 1)
    years = {s.year: s for s in analysis.annual_summaries}
    assert not years[2023].eligible_for_trend_inference
    assert years[2024].eligible_for_trend_inference


def test_the_two_versions_produce_independent_results() -> None:
    v5 = analyze_series(smap_series(SMAP5, SMAP5_AVAIL, date(2023, 1, 1), date(2025, 1, 1)),
                        SMAP5, TREND)
    v6 = analyze_series(smap_series(SMAP6, SMAP6_AVAIL, date(2023, 1, 1), date(2025, 1, 1)),
                        SMAP6, TREND)
    e5 = {s.year for s in v5.annual_summaries if s.eligible_for_trend_inference}
    e6 = {s.year for s in v6.annual_summaries if s.eligible_for_trend_inference}
    assert e5 == set() and e6 == {2024}
    assert v5.dataset_key != v6.dataset_key and v5.collection_id != v6.collection_id


# --- trend integration --------------------------------------------------------


def golden_gldas() -> MonthlySoilMoistureSeries:
    return gldas_series(date(2015, 1, 1), date(2025, 1, 1),
                        value=lambda m: 20.0 + 0.5 * (m.year - 2015) + GOLDEN_NOISE[m.year - 2015])


def test_golden_series_recovers_known_slope_with_full_inference() -> None:
    trend = analyze_series(golden_gldas(), GLDAS, TREND).trend
    assert trend.result_level == "statistical_inference"
    assert trend.eligible_years == tuple(range(2015, 2025))
    assert trend.theil_sen.slope == pytest.approx(0.5, abs=1e-9)
    assert trend.theil_sen.slope_units == "kg m-2/year"
    assert trend.mann_kendall is not None
    assert trend.mann_kendall.alternative == "two-sided"


def test_derived_trend_is_native_trend_scaled_with_identical_mann_kendall() -> None:
    analysis = analyze_series(golden_gldas(), GLDAS, TREND)
    native, derived = analysis.trend, analysis.derived_trend
    assert derived.result_level == native.result_level
    assert derived.theil_sen.slope == pytest.approx(native.theil_sen.slope / 100, abs=1e-12)
    assert derived.theil_sen.slope == pytest.approx(0.005, abs=1e-11)
    assert derived.theil_sen.slope_units == "m3 m-3/year"
    lo, hi = native.theil_sen.confidence_interval
    dlo, dhi = derived.theil_sen.confidence_interval
    assert (dlo, dhi) == (pytest.approx(lo / 100, abs=1e-12), pytest.approx(hi / 100, abs=1e-12))
    assert derived.mann_kendall.s == native.mann_kendall.s
    assert derived.mann_kendall.tau == pytest.approx(native.mann_kendall.tau, abs=1e-15)
    assert derived.mann_kendall.p_value == pytest.approx(native.mann_kendall.p_value, abs=1e-15)


def test_trend_matches_a_direct_engine_call() -> None:
    analysis = analyze_series(golden_gldas(), GLDAS, TREND)
    assert analysis.trend == analyze_trend(analysis.annual_summaries, "kg m-2", TREND)


def test_seven_eligible_years_give_slope_without_significance() -> None:
    series = smap_series(SMAP5, SMAP5_AVAIL, date(2016, 1, 1), date(2023, 1, 1),
                         value=lambda m: 0.20 + 0.003 * (m.year - 2016) + 0.001 * (m.year % 3))
    trend = analyze_series(series, SMAP5, TREND).trend
    assert trend.result_level == "descriptive_slope"
    assert len(trend.eligible_years) == 7
    assert trend.mann_kendall is None
    assert "8 eligible annual observations" in trend.significance_unavailable_reason
    assert trend.theil_sen.slope_units == "m3 m-3/year"


def test_two_eligible_years_give_annual_summaries_only() -> None:
    trend = analyze_series(smap_series(SMAP6, SMAP6_AVAIL, date(2023, 12, 1), date(2026, 1, 1)),
                           SMAP6, TREND).trend
    assert trend.result_level == "annual_summaries_only"
    assert trend.eligible_years == (2024, 2025)
    assert trend.theil_sen is None
    assert "3 eligible annual observations" in trend.slope_unavailable_reason


def test_excluded_years_carry_stable_engine_reasons() -> None:
    series = gldas_series(date(2014, 6, 1), date(2025, 1, 1),
                          value=lambda m: 20.0 + 0.5 * (m.year - 2015) + GOLDEN_NOISE[max(0, m.year - 2015)],
                          skip={date(2018, 2, 1)})
    trend = analyze_series(series, GLDAS, TREND).trend
    excluded = dict(trend.excluded_years)
    assert "partial_calendar_year" in excluded[2014]
    assert "insufficient_represented_months" in excluded[2018]
    assert 2018 in trend.missing_years
    assert 2018 not in trend.eligible_years


# --- engine unchanged ---------------------------------------------------------


def test_shared_engine_public_signatures_are_unchanged() -> None:
    assert list(inspect.signature(aggregate_annual).parameters) == ["series", "policy"]
    assert list(inspect.signature(analyze_trend).parameters) == ["summaries", "value_units", "policy"]
