from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta

import pytest

from app.soil_moisture.aggregation import annual_policy, assess_months, year_support
from app.soil_moisture.datasets import get_dataset
from app.soil_moisture.models import (
    CatalogAvailability,
    MonthFlag,
    MonthlySample,
    MonthlySoilMoisture,
    MonthlySoilMoistureSeries,
    MonthStatus,
    SupportPolicy,
    expected_slots,
)
from app.statistics.policies import AnnualAggregationPolicy


GLDAS = get_dataset("gldas_2_1_noah_0_10cm")
SMAP5 = get_dataset("smap_l3e_v005_am")
SMAP6 = get_dataset("smap_l3e_v006_am")

GLDAS_AVAIL = CatalogAvailability(
    "NASA/GLDAS/V021/NOAH/G025/T3H", date(2000, 1, 1), date(2026, 10, 15)
)
SMAP5_AVAIL = CatalogAvailability("NASA/SMAP/SPL3SMP_E/005", date(2015, 3, 31), date(2023, 12, 3))
SMAP6_AVAIL = CatalogAvailability("NASA/SMAP/SPL3SMP_E/006", date(2023, 12, 4), date(2026, 11, 10))
POLICY = SupportPolicy()


def gldas_sample(month: date, valid: int | None = None, mean: float | None = 24.0,
                 images: int | None = None) -> MonthlySample:
    slots = expected_slots(GLDAS, month)
    valid = slots if valid is None else valid
    return MonthlySample(
        month=month,
        available_images=slots if images is None else images,
        valid_values=valid,
        mean_native=None if valid == 0 else mean,
    )


def smap_sample(month: date, days: list[int], mean: float = 0.21,
                images: int | None = None) -> MonthlySample:
    dates = tuple(month.replace(day=d) for d in days)
    return MonthlySample(
        month=month,
        available_images=(len(dates) if images is None else images),
        valid_values=len(dates),
        mean_native=mean if dates else None,
        valid_dates=dates,
    )


def one(descriptor, sample, availability, policy=POLICY) -> MonthlySoilMoisture:
    start = sample.month
    end = (start + timedelta(days=32)).replace(day=1)
    (record,) = assess_months(descriptor, (sample,), availability, start, end, policy).months
    return record


# --- policy -------------------------------------------------------------------


def test_default_policy_matches_approved_provisional_values() -> None:
    assert POLICY.gldas_min_slot_coverage == 0.90
    assert POLICY.gldas_provisional_recent_months == 4
    assert POLICY.smap_min_valid_days == 8
    assert POLICY.smap_min_valid_days_per_third == 1


def test_policy_is_labelled_provisional_not_a_universal_standard() -> None:
    assert POLICY.is_universal_standard is False
    assert POLICY.status == "provisional_pending_live_validation"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"gldas_min_slot_coverage": 0.0}, "slot coverage"),
        ({"gldas_min_slot_coverage": 1.01}, "slot coverage"),
        ({"gldas_provisional_recent_months": -1}, "provisional"),
        ({"smap_min_valid_days": 0}, "valid days"),
        ({"smap_min_valid_days": 32}, "valid days"),
        ({"smap_min_valid_days_per_third": -1}, "per third"),
        ({"smap_min_valid_days_per_third": 11}, "per third"),
    ],
)
def test_policy_rejects_out_of_range_settings(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SupportPolicy(**kwargs)


def test_policy_exclusion_window_is_configurable() -> None:
    assert SupportPolicy(gldas_provisional_recent_months=0).gldas_provisional_recent_months == 0


# --- expected slots -----------------------------------------------------------


@pytest.mark.parametrize(
    "month, slots",
    [
        (date(2000, 1, 1), 247),   # record starts 2000-01-01T03Z
        (date(2000, 2, 1), 232),   # leap February
        (date(2021, 2, 1), 224),
        (date(2020, 4, 1), 240),
        (date(2020, 12, 1), 248),
    ],
)
def test_gldas_expected_slots_come_from_the_calendar(month: date, slots: int) -> None:
    assert expected_slots(GLDAS, month) == slots


def test_smap_expected_slots_are_calendar_days() -> None:
    assert expected_slots(SMAP5, date(2020, 2, 1)) == 29
    assert expected_slots(SMAP5, date(2021, 6, 1)) == 30


def test_expected_slots_requires_first_of_month() -> None:
    with pytest.raises(ValueError, match="first"):
        expected_slots(GLDAS, date(2020, 1, 2))


# --- sample validation (valid and invalid values) -----------------------------


def test_sample_rejects_non_finite_mean() -> None:
    with pytest.raises(ValueError, match="finite"):
        MonthlySample(date(2020, 1, 1), 248, 248, float("nan"))


def test_sample_requires_mean_exactly_when_values_exist() -> None:
    with pytest.raises(ValueError, match="mean"):
        MonthlySample(date(2020, 1, 1), 248, 248, None)
    with pytest.raises(ValueError, match="mean"):
        MonthlySample(date(2020, 1, 1), 248, 0, 0.0)


def test_sample_rejects_negative_counts_and_valid_above_images() -> None:
    with pytest.raises(ValueError, match="negative"):
        MonthlySample(date(2020, 1, 1), -1, 0, None)
    with pytest.raises(ValueError, match="exceed"):
        MonthlySample(date(2020, 1, 1), 10, 11, 20.0)


def test_sample_valid_dates_must_be_unique_in_month_and_match_count() -> None:
    m = date(2020, 6, 1)
    with pytest.raises(ValueError, match="unique"):
        MonthlySample(m, 2, 2, 0.2, (date(2020, 6, 3), date(2020, 6, 3)))
    with pytest.raises(ValueError, match="within the month"):
        MonthlySample(m, 1, 1, 0.2, (date(2020, 7, 1),))
    with pytest.raises(ValueError, match="valid_values"):
        MonthlySample(m, 3, 3, 0.2, (date(2020, 6, 3),))


def test_gldas_mean_outside_layer_capacity_is_a_provider_anomaly() -> None:
    with pytest.raises(ValueError, match="valid range"):
        one(GLDAS, gldas_sample(date(2020, 1, 1), mean=100.5), GLDAS_AVAIL)
    with pytest.raises(ValueError, match="valid range"):
        one(GLDAS, gldas_sample(date(2020, 1, 1), mean=-0.1), GLDAS_AVAIL)


def test_smap_mean_outside_unit_interval_is_a_provider_anomaly() -> None:
    with pytest.raises(ValueError, match="valid range"):
        one(SMAP5, smap_sample(date(2020, 6, 1), list(range(1, 31, 3)), mean=1.2), SMAP5_AVAIL)


def test_counts_above_expected_slots_are_rejected() -> None:
    with pytest.raises(ValueError, match="expected"):
        one(GLDAS, gldas_sample(date(2020, 4, 1), images=241, valid=240), GLDAS_AVAIL)


def test_genuine_zero_is_kept_not_treated_as_missing() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1), mean=0.0), GLDAS_AVAIL)
    assert record.status is MonthStatus.VALID
    assert record.mean_native == 0.0


# --- GLDAS monthly support ----------------------------------------------------


def test_gldas_full_month_is_valid() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1)), GLDAS_AVAIL)
    assert record.status is MonthStatus.VALID
    assert (record.expected_slots, record.available_images, record.valid_values) == (248, 248, 248)
    assert record.slot_coverage == 1.0
    assert record.mean_native == 24.0
    assert record.usable_for_inference


def test_gldas_below_slot_coverage_is_withheld_but_described() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=220), GLDAS_AVAIL)
    assert record.status is MonthStatus.INSUFFICIENT_SUPPORT
    assert record.mean_native is None
    assert record.descriptive_mean_native == 24.0
    assert record.slot_coverage == pytest.approx(220 / 248)
    assert not record.usable_for_inference


def test_gldas_threshold_boundary_is_inclusive() -> None:
    # 0.90 * 240 = 216 exactly
    assert one(GLDAS, gldas_sample(date(2020, 4, 1), valid=216), GLDAS_AVAIL).status is MonthStatus.VALID
    assert one(GLDAS, gldas_sample(date(2020, 4, 1), valid=215), GLDAS_AVAIL).status is (
        MonthStatus.INSUFFICIENT_SUPPORT
    )


def test_gldas_partial_month_that_passes_is_flagged_partial() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 4, 1), valid=230), GLDAS_AVAIL)
    assert record.status is MonthStatus.VALID
    assert MonthFlag.PARTIAL_TEMPORAL_SUPPORT in record.flags


def test_gldas_images_present_do_not_imply_valid_values() -> None:
    # Regular cadence does not guarantee valid data at the cell.
    record = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=0), GLDAS_AVAIL)
    assert record.status is MonthStatus.NO_VALID_VALUES
    assert record.available_images == 248
    assert record.mean_native is None and record.descriptive_mean_native is None


def test_missing_sample_inside_availability_is_no_images() -> None:
    series = assess_months(GLDAS, (), GLDAS_AVAIL, date(2020, 1, 1), date(2020, 2, 1), POLICY)
    (record,) = series.months
    assert record.status is MonthStatus.NO_IMAGES
    assert record.available_images == 0
    assert record.mean_native is None


def test_zero_images_sample_is_no_images() -> None:
    record = one(GLDAS, MonthlySample(date(2020, 1, 1), 0, 0, None), GLDAS_AVAIL)
    assert record.status is MonthStatus.NO_IMAGES


def test_first_gldas_month_uses_247_slots() -> None:
    record = one(GLDAS, gldas_sample(date(2000, 1, 1)), GLDAS_AVAIL)
    assert record.expected_slots == 247 and record.status is MonthStatus.VALID


# --- GLDAS recent-month exclusion (D2) ----------------------------------------


def test_gldas_months_within_window_of_latest_image_are_provisional() -> None:
    samples = tuple(gldas_sample(date(2026, m, 1)) for m in range(5, 11))
    series = assess_months(GLDAS, samples, GLDAS_AVAIL, date(2026, 5, 1), date(2026, 11, 1), POLICY)
    flagged = {r.month.month for r in series.months if MonthFlag.PROVISIONAL_RECENT_PRODUCT in r.flags}
    # latest image 2026-10-15; 4 months back = 2026-06-15; months starting after it
    assert flagged == {7, 8, 9, 10}


def test_provisional_months_keep_status_and_value_but_are_not_usable_for_inference() -> None:
    record = one(GLDAS, gldas_sample(date(2026, 9, 1)), GLDAS_AVAIL)
    assert record.status is MonthStatus.VALID
    assert record.mean_native == 24.0
    assert not record.usable_for_inference
    assert record.inference_exclusion_reasons == ("provisional_recent_product",)


def test_window_is_anchored_to_catalog_latest_image_not_today() -> None:
    older_catalog = CatalogAvailability(GLDAS_AVAIL.collection_id, date(2000, 1, 1), date(2021, 3, 20))
    series = assess_months(
        GLDAS,
        tuple(gldas_sample(date(2020, m, 1)) for m in range(10, 13)),
        older_catalog, date(2020, 10, 1), date(2021, 1, 1), POLICY,
    )
    flagged = [r.month for r in series.months if MonthFlag.PROVISIONAL_RECENT_PRODUCT in r.flags]
    assert flagged == [date(2020, 12, 1)]  # 2021-03-20 minus 4 months = 2020-11-20


def test_exclusion_window_can_be_disabled() -> None:
    record = one(GLDAS, gldas_sample(date(2026, 9, 1)), GLDAS_AVAIL,
                 SupportPolicy(gldas_provisional_recent_months=0))
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT not in record.flags
    assert record.usable_for_inference


def test_provisional_flag_does_not_assert_product_stream() -> None:
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT.value == "provisional_recent_product"
    assert "early" not in MonthFlag.PROVISIONAL_RECENT_PRODUCT.value


def test_recent_month_exclusion_is_not_applied_to_smap() -> None:
    record = one(SMAP6, smap_sample(date(2026, 10, 1), [1, 3, 6, 9, 12, 15, 21, 24, 27]), SMAP6_AVAIL)
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT not in record.flags
    assert record.usable_for_inference


# --- SMAP temporal sampling (D5) ----------------------------------------------


def test_smap_eight_well_spread_days_is_valid() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25, 28]), SMAP5_AVAIL)
    assert record.status is MonthStatus.VALID
    assert record.valid_days_by_third == (3, 2, 3)
    assert record.missing_thirds == ()
    assert record.mean_native == 0.21
    assert record.value_definition == "mean of valid sampled days"


def test_smap_seven_days_is_insufficient_support() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25]), SMAP5_AVAIL)
    assert record.status is MonthStatus.INSUFFICIENT_SUPPORT
    assert record.mean_native is None
    assert record.descriptive_mean_native == 0.21


def test_smap_clustered_days_fail_temporal_spread() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), SMAP5_AVAIL)
    assert record.status is MonthStatus.INSUFFICIENT_TEMPORAL_SPREAD
    assert record.valid_days_by_third == (10, 0, 0)
    assert record.missing_thirds == (2, 3)
    assert record.mean_native is None
    assert record.descriptive_mean_native == 0.21


def test_smap_final_third_runs_to_month_end() -> None:
    record = one(SMAP5, smap_sample(date(2020, 1, 1), [2, 4, 6, 12, 14, 16, 31, 18]), SMAP5_AVAIL)
    assert record.valid_days_by_third == (3, 4, 1)
    assert record.status is MonthStatus.VALID


def test_smap_longest_gap_includes_month_edges() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [5, 8, 11, 14, 17, 20, 21, 22]), SMAP5_AVAIL)
    # days 23-30 have no retrieval: 8 days
    assert record.longest_gap_days == 8


def test_smap_counts_and_opportunities_are_recorded() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25, 28], images=30),
                 SMAP5_AVAIL)
    assert record.available_images == 30
    assert record.valid_values == 8
    assert record.expected_slots == 30


def test_smap_no_valid_days_is_no_valid_values_with_whole_month_gap() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [], images=30), SMAP5_AVAIL)
    assert record.status is MonthStatus.NO_VALID_VALUES
    assert record.longest_gap_days == 30
    assert record.missing_thirds == (1, 2, 3)


def test_smap_samples_require_valid_dates() -> None:
    with pytest.raises(ValueError, match="valid dates"):
        one(SMAP5, MonthlySample(date(2020, 6, 1), 10, 10, 0.2), SMAP5_AVAIL)


def test_smap_thresholds_are_configurable() -> None:
    strict = SupportPolicy(smap_min_valid_days=10)
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25, 28]), SMAP5_AVAIL, strict)
    assert record.status is MonthStatus.INSUFFICIENT_SUPPORT


# --- availability and version boundaries --------------------------------------


def test_months_outside_catalog_availability_are_marked_not_filled() -> None:
    samples = (
        smap_sample(date(2023, 10, 1), [2, 5, 8, 12, 15, 22, 25, 28]),
        smap_sample(date(2023, 11, 1), [2, 5, 8, 12, 15, 22, 25, 28]),
        smap_sample(date(2023, 12, 1), [1, 2, 3]),
    )
    series = assess_months(SMAP5, samples, SMAP5_AVAIL, date(2023, 10, 1), date(2024, 3, 1), POLICY)
    statuses = {r.month: r.status for r in series.months}
    assert statuses[date(2024, 1, 1)] is MonthStatus.OUTSIDE_AVAILABILITY
    assert statuses[date(2024, 2, 1)] is MonthStatus.OUTSIDE_AVAILABILITY
    for r in series.months:
        if r.status is MonthStatus.OUTSIDE_AVAILABILITY:
            assert r.mean_native is None and r.descriptive_mean_native is None


def test_boundary_month_is_flagged_partial_catalog_and_not_completed_from_other_version() -> None:
    v5 = one(SMAP5, smap_sample(date(2023, 12, 1), [1, 2, 3]), SMAP5_AVAIL)
    assert MonthFlag.PARTIAL_CATALOG_MONTH in v5.flags
    assert v5.status is MonthStatus.INSUFFICIENT_SUPPORT
    assert v5.dataset_key == "smap_l3e_v005_am"

    v6 = one(SMAP6, smap_sample(date(2023, 12, 1), [4, 6, 9, 12, 15, 18, 22, 26, 30]), SMAP6_AVAIL)
    assert MonthFlag.PARTIAL_CATALOG_MONTH in v6.flags
    assert v6.status is MonthStatus.VALID
    assert v6.dataset_key == "smap_l3e_v006_am"


def test_v006_months_before_its_collection_are_outside_availability() -> None:
    series = assess_months(SMAP6, (), SMAP6_AVAIL, date(2023, 10, 1), date(2023, 12, 1), POLICY)
    assert all(r.status is MonthStatus.OUTSIDE_AVAILABILITY for r in series.months)


def test_availability_for_another_collection_is_rejected() -> None:
    with pytest.raises(ValueError, match="collection"):
        assess_months(SMAP5, (), SMAP6_AVAIL, date(2023, 1, 1), date(2023, 2, 1), POLICY)


def test_data_reported_outside_availability_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside catalog availability"):
        assess_months(SMAP5, (smap_sample(date(2024, 1, 1), [2, 5, 8]),), SMAP5_AVAIL,
                      date(2024, 1, 1), date(2024, 2, 1), POLICY)


def test_catalog_availability_rejects_inverted_dates() -> None:
    with pytest.raises(ValueError, match="availability"):
        CatalogAvailability("X/Y", date(2020, 2, 1), date(2020, 1, 1))


# --- series validation --------------------------------------------------------


def test_one_record_per_requested_month_in_order() -> None:
    series = assess_months(GLDAS, (), GLDAS_AVAIL, date(2019, 11, 1), date(2020, 3, 1), POLICY)
    assert [r.month for r in series.months] == [
        date(2019, 11, 1), date(2019, 12, 1), date(2020, 1, 1), date(2020, 2, 1)
    ]


def test_duplicate_samples_are_rejected() -> None:
    s = gldas_sample(date(2020, 1, 1))
    with pytest.raises(ValueError, match="duplicate"):
        assess_months(GLDAS, (s, s), GLDAS_AVAIL, date(2020, 1, 1), date(2020, 2, 1), POLICY)


def test_samples_outside_request_are_rejected() -> None:
    with pytest.raises(ValueError, match="outside the requested period"):
        assess_months(GLDAS, (gldas_sample(date(2019, 12, 1)),), GLDAS_AVAIL,
                      date(2020, 1, 1), date(2020, 2, 1), POLICY)


def test_request_bounds_must_be_month_starts_and_ordered() -> None:
    with pytest.raises(ValueError, match="first day"):
        assess_months(GLDAS, (), GLDAS_AVAIL, date(2020, 1, 2), date(2020, 3, 1), POLICY)
    with pytest.raises(ValueError, match="after"):
        assess_months(GLDAS, (), GLDAS_AVAIL, date(2020, 3, 1), date(2020, 3, 1), POLICY)


def test_series_rejects_duplicate_or_mixed_dataset_records() -> None:
    a = one(GLDAS, gldas_sample(date(2020, 1, 1)), GLDAS_AVAIL)
    b = one(SMAP5, smap_sample(date(2020, 2, 1), [2, 5, 8, 12, 15, 22, 25, 28]), SMAP5_AVAIL)
    with pytest.raises(ValueError, match="duplicate"):
        MonthlySoilMoistureSeries("gldas_2_1_noah_0_10cm", (a, a))
    with pytest.raises(ValueError, match="single dataset"):
        MonthlySoilMoistureSeries("gldas_2_1_noah_0_10cm", (a, b))


# --- missing-data semantics (regression) --------------------------------------


def test_missing_sample_month_has_no_descriptive_mean() -> None:
    series = assess_months(GLDAS, (), GLDAS_AVAIL, date(2020, 1, 1), date(2020, 2, 1), POLICY)
    (record,) = series.months
    assert record.mean_native is None
    assert record.descriptive_mean_native is None
    assert record.derived_volumetric is None


def test_zero_image_month_has_no_descriptive_mean() -> None:
    record = one(GLDAS, MonthlySample(date(2020, 1, 1), 0, 0, None), GLDAS_AVAIL)
    assert record.descriptive_mean_native is None


def test_smap_month_without_valid_days_has_no_descriptive_mean() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [], images=30), SMAP5_AVAIL)
    assert record.status is MonthStatus.NO_VALID_VALUES
    assert record.mean_native is None
    assert record.descriptive_mean_native is None


def test_smap_month_with_no_images_has_no_descriptive_mean() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), []), SMAP5_AVAIL)
    assert record.status is MonthStatus.NO_IMAGES
    assert record.descriptive_mean_native is None


def test_incomplete_months_with_valid_values_keep_a_descriptive_mean() -> None:
    gldas = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=1, mean=30.0), GLDAS_AVAIL)
    smap = one(SMAP5, smap_sample(date(2020, 6, 1), [4]), SMAP5_AVAIL)
    assert (gldas.status, gldas.descriptive_mean_native) == (MonthStatus.INSUFFICIENT_SUPPORT, 30.0)
    assert (smap.status, smap.descriptive_mean_native) == (MonthStatus.INSUFFICIENT_SUPPORT, 0.21)
    assert not gldas.usable_for_inference and not smap.usable_for_inference


def test_record_rejects_descriptive_mean_without_valid_values() -> None:
    template = one(GLDAS, MonthlySample(date(2020, 1, 1), 0, 0, None), GLDAS_AVAIL)
    with pytest.raises(ValueError, match="descriptive mean"):
        replace(template, descriptive_mean_native=0.0)


def test_record_rejects_valid_values_without_descriptive_mean() -> None:
    template = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=10), GLDAS_AVAIL)
    with pytest.raises(ValueError, match="descriptive mean"):
        replace(template, descriptive_mean_native=None)


@pytest.mark.parametrize(
    "status",
    [MonthStatus.INSUFFICIENT_SUPPORT, MonthStatus.INSUFFICIENT_TEMPORAL_SPREAD,
     MonthStatus.NO_IMAGES, MonthStatus.NO_VALID_VALUES, MonthStatus.OUTSIDE_AVAILABILITY],
)
def test_non_valid_statuses_are_never_usable_for_inference(status: MonthStatus) -> None:
    template = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=10), GLDAS_AVAIL)
    record = replace(template, status=status)
    assert not record.usable_for_inference
    assert record.inference_exclusion_reasons[0] == status.value


def test_records_are_frozen() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1)), GLDAS_AVAIL)
    with pytest.raises(FrozenInstanceError):
        record.mean_native = 1.0  # type: ignore[misc]


# --- units consistency --------------------------------------------------------


def test_gldas_record_carries_storage_units_and_derived_layer_mean() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1), mean=25.0), GLDAS_AVAIL)
    assert record.units == "kg m-2"
    assert record.derived_units == "m3 m-3"
    assert record.derived_volumetric == pytest.approx(0.25, abs=1e-12)
    assert record.value_definition == "mean of 3-hourly instantaneous layer states"


def test_withheld_gldas_month_has_no_derived_value() -> None:
    record = one(GLDAS, gldas_sample(date(2020, 1, 1), valid=100, mean=25.0), GLDAS_AVAIL)
    assert record.derived_volumetric is None


def test_smap_record_is_volumetric_with_no_derived_value() -> None:
    record = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25, 28]), SMAP5_AVAIL)
    assert record.units == "m3 m-3"
    assert record.derived_units is None
    assert record.derived_volumetric is None


def test_record_keeps_dataset_identity_and_version() -> None:
    r5 = one(SMAP5, smap_sample(date(2020, 6, 1), [2, 5, 8, 12, 15, 22, 25, 28]), SMAP5_AVAIL)
    assert (r5.dataset_key, r5.collection_id, r5.version) == (
        "smap_l3e_v005_am", "NASA/SMAP/SPL3SMP_E/005", "005"
    )


# --- annual eligibility infrastructure and partial years ----------------------


def test_annual_policy_is_twelve_of_twelve_complete_years() -> None:
    for descriptor in (GLDAS, SMAP5, SMAP6):
        policy = annual_policy(descriptor)
        assert isinstance(policy, AnnualAggregationPolicy)
        assert policy.minimum_represented_months == 12
        assert policy.minimum_valid_slot_coverage == 1.0
        assert policy.require_all_quarters is True
        assert policy.exclude_partial_calendar_years_from_inference is True


def test_year_support_reports_complete_year_counts() -> None:
    samples = tuple(gldas_sample(date(2020, m, 1)) for m in range(1, 13))
    series = assess_months(GLDAS, samples, GLDAS_AVAIL, date(2020, 1, 1), date(2021, 1, 1), POLICY)
    (year,) = year_support(series)
    assert year.year == 2020
    assert year.is_complete_calendar_year
    assert year.requested_months == 12
    assert year.usable_months == 12
    assert year.missing_months == ()


def test_year_support_lists_missing_months_with_reasons() -> None:
    samples = [gldas_sample(date(2020, m, 1)) for m in range(1, 13) if m != 3]
    samples[5] = gldas_sample(date(2020, 7, 1), valid=10)
    series = assess_months(GLDAS, tuple(samples), GLDAS_AVAIL, date(2020, 1, 1), date(2021, 1, 1), POLICY)
    (year,) = year_support(series)
    assert year.usable_months == 10
    assert year.missing_months == ((3, "no_images"), (7, "insufficient_support"))


def test_partial_years_are_identified_and_kept_descriptively() -> None:
    samples = tuple(gldas_sample(date(y, m, 1)) for y, m in [(2019, 11), (2019, 12), (2020, 1), (2020, 2)])
    series = assess_months(GLDAS, samples, GLDAS_AVAIL, date(2019, 11, 1), date(2020, 3, 1), POLICY)
    years = year_support(series)
    assert [(y.year, y.is_complete_calendar_year, y.requested_months, y.usable_months) for y in years] == [
        (2019, False, 2, 2),
        (2020, False, 2, 2),
    ]


def test_year_support_counts_provisional_months_as_not_usable() -> None:
    samples = tuple(gldas_sample(date(2026, m, 1)) for m in range(1, 11))
    series = assess_months(GLDAS, samples, GLDAS_AVAIL, date(2026, 1, 1), date(2026, 11, 1), POLICY)
    (year,) = year_support(series)
    assert year.usable_months == 6
    assert (7, "provisional_recent_product") in year.missing_months


# --- property-based provisional status (catalog "status" verified live) -------


def _with_status(month: date, nonpermanent: int) -> MonthlySample:
    slots = expected_slots(GLDAS, month)
    return MonthlySample(month, slots, slots, 24.0, None, nonpermanent)


def test_catalog_status_overrides_time_window_when_known() -> None:
    # July 2026 is inside the 4-month window but every image is "permanent".
    permanent = one(GLDAS, _with_status(date(2026, 7, 1), 0), GLDAS_AVAIL)
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT not in permanent.flags
    assert permanent.usable_for_inference


def test_any_nonpermanent_image_marks_the_month_provisional() -> None:
    early = one(GLDAS, _with_status(date(2020, 1, 1), 1), GLDAS_AVAIL)
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT in early.flags
    assert early.status is MonthStatus.VALID and not early.usable_for_inference


def test_unknown_status_falls_back_to_time_window() -> None:
    record = one(GLDAS, gldas_sample(date(2026, 9, 1)), GLDAS_AVAIL)
    assert MonthFlag.PROVISIONAL_RECENT_PRODUCT in record.flags


def test_nonpermanent_count_is_validated() -> None:
    with pytest.raises(ValueError, match="nonpermanent"):
        MonthlySample(date(2020, 1, 1), 10, 10, 20.0, None, 11)
    with pytest.raises(ValueError, match="nonpermanent"):
        MonthlySample(date(2020, 1, 1), 10, 10, 20.0, None, -1)
