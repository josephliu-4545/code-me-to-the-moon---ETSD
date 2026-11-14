"""Pure monthly support assessment for one soil moisture dataset.

Every requested calendar month gets exactly one record. Missing, masked, or
outside-availability months are never zero and are never filled from another
dataset or another version.
"""

from collections import defaultdict
from datetime import date, timedelta

from app.soil_moisture.datasets import DatasetDescriptor
from app.soil_moisture.models import (
    CatalogAvailability,
    MonthFlag,
    MonthlySample,
    MonthlySoilMoisture,
    MonthlySoilMoistureSeries,
    MonthStatus,
    SoilMoistureAnalysis,
    SupportPolicy,
    YearSupport,
    days_in_month,
    expected_slots,
)
from app.soil_moisture.units import storage_to_volumetric
from app.statistics.annual import aggregate_annual
from app.statistics.models import ObservationSeries, TimedValue, YearCoverage
from app.statistics.policies import AnnualAggregationPolicy, TrendPolicy
from app.statistics.trend import analyze_trend


_VALUE_DEFINITIONS = {
    True: "mean of 3-hourly instantaneous layer states",   # model
    False: "mean of valid sampled days",                     # satellite
}


def _next_month(month: date) -> date:
    return (month + timedelta(days=32)).replace(day=1)


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month0 = divmod(index, 12)
    first = date(year, month0 + 1, 1)
    return first.replace(day=min(day.day, days_in_month(first)))


def _third(day: int) -> int:
    return 0 if day <= 10 else 1 if day <= 20 else 2


def _longest_gap(month: date, valid_dates: tuple[date, ...]) -> int:
    days = sorted(d.day for d in valid_dates)
    edges = [0, *days, days_in_month(month) + 1]
    return max(b - a - 1 for a, b in zip(edges, edges[1:]))


def _assess(
    descriptor: DatasetDescriptor,
    month: date,
    sample: MonthlySample | None,
    availability: CatalogAvailability,
    policy: SupportPolicy,
) -> MonthlySoilMoisture:
    month_end = _next_month(month) - timedelta(days=1)
    slots = expected_slots(descriptor, month)
    is_model = descriptor.is_model
    common = dict(
        dataset_key=descriptor.key,
        collection_id=descriptor.collection_ids[0],
        version=descriptor.version,
        month=month,
        expected_slots=slots,
        units=descriptor.native_units,
        derived_units="m3 m-3" if descriptor.supports_derived_volumetric else None,
        value_definition=_VALUE_DEFINITIONS[is_model],
    )

    if month_end < availability.first_image_date or month > availability.last_image_date:
        if sample is not None and sample.available_images > 0:
            raise ValueError(f"{month:%Y-%m} has data outside catalog availability")
        return MonthlySoilMoisture(
            status=MonthStatus.OUTSIDE_AVAILABILITY, flags=(), available_images=0,
            valid_values=0, mean_native=None, descriptive_mean_native=None,
            derived_volumetric=None, **common,
        )

    sample = sample or MonthlySample(month, 0, 0, None, None if is_model else ())
    if sample.available_images > slots or sample.valid_values > slots:
        raise ValueError(f"{month:%Y-%m} reports more values than expected slots ({slots})")
    if sample.mean_native is not None:
        low, high = descriptor.valid_range
        if not low <= sample.mean_native <= high:
            raise ValueError(
                f"{month:%Y-%m} mean {sample.mean_native} is outside the valid range "
                f"[{low}, {high}] {descriptor.native_units}"
            )

    flags: list[MonthFlag] = []
    if month < availability.first_image_date or month_end > availability.last_image_date:
        flags.append(MonthFlag.PARTIAL_CATALOG_MONTH)
    if is_model:
        if sample.nonpermanent_images is not None:
            # Catalog-declared product status (verified live: "permanent" / "early").
            provisional = sample.nonpermanent_images > 0
        else:
            # Status unknown: conservative window before the catalog's latest image.
            provisional = (policy.gldas_provisional_recent_months > 0 and month > _shift_months(
                availability.last_image_date, -policy.gldas_provisional_recent_months))
        if provisional:
            flags.append(MonthFlag.PROVISIONAL_RECENT_PRODUCT)

    spread: dict = {}
    if not is_model:
        if sample.valid_dates is None:
            raise ValueError("daily satellite samples require valid dates")
        if any(not availability.first_image_date <= d <= availability.last_image_date
               for d in sample.valid_dates):
            raise ValueError(f"{month:%Y-%m} has valid dates outside catalog availability")
        thirds = [0, 0, 0]
        for d in sample.valid_dates:
            thirds[_third(d.day)] += 1
        spread = dict(
            valid_days_by_third=tuple(thirds),
            missing_thirds=tuple(i + 1 for i, n in enumerate(thirds) if n == 0),
            longest_gap_days=_longest_gap(month, sample.valid_dates),
        )

    if sample.available_images == 0:
        status = MonthStatus.NO_IMAGES
    elif sample.valid_values == 0:
        status = MonthStatus.NO_VALID_VALUES
    elif is_model:
        coverage = sample.valid_values / slots
        status = (MonthStatus.VALID if coverage >= policy.gldas_min_slot_coverage
                  else MonthStatus.INSUFFICIENT_SUPPORT)
        if status is MonthStatus.VALID and sample.valid_values < slots:
            flags.append(MonthFlag.PARTIAL_TEMPORAL_SUPPORT)
    elif sample.valid_values < policy.smap_min_valid_days:
        status = MonthStatus.INSUFFICIENT_SUPPORT
    elif min(spread["valid_days_by_third"]) < policy.smap_min_valid_days_per_third:
        status = MonthStatus.INSUFFICIENT_TEMPORAL_SPREAD
    else:
        status = MonthStatus.VALID

    published = sample.mean_native if status is MonthStatus.VALID else None
    derived = None
    if published is not None and descriptor.supports_derived_volumetric:
        derived = storage_to_volumetric(
            published, descriptor.depth_top_cm, descriptor.depth_bottom_cm,
            quantity_kind=descriptor.quantity_kind,
        )
    return MonthlySoilMoisture(
        status=status, flags=tuple(flags), available_images=sample.available_images,
        valid_values=sample.valid_values, mean_native=published,
        descriptive_mean_native=sample.mean_native, derived_volumetric=derived,
        **common, **spread,
    )


def assess_months(
    descriptor: DatasetDescriptor,
    samples: tuple[MonthlySample, ...],
    availability: CatalogAvailability,
    start: date,
    end: date,
    policy: SupportPolicy,
) -> MonthlySoilMoistureSeries:
    """Assess every calendar month in ``[start, end)`` for one dataset."""
    if start.day != 1 or end.day != 1:
        raise ValueError("request bounds must be the first day of a month")
    if end <= start:
        raise ValueError("end must be after start")
    if availability.collection_id != descriptor.collection_ids[0]:
        raise ValueError(
            f"availability is for collection {availability.collection_id!r}, "
            f"not {descriptor.collection_ids[0]!r}"
        )

    by_month: dict[date, MonthlySample] = {}
    for sample in samples:
        if sample.month in by_month:
            raise ValueError(f"duplicate sample for {sample.month:%Y-%m}")
        if not start <= sample.month < end:
            raise ValueError(f"sample {sample.month:%Y-%m} is outside the requested period")
        by_month[sample.month] = sample

    records = []
    month = start
    while month < end:
        records.append(_assess(descriptor, month, by_month.get(month), availability, policy))
        month = _next_month(month)
    return MonthlySoilMoistureSeries(descriptor.key, tuple(records))


def year_support(series: MonthlySoilMoistureSeries) -> tuple[YearSupport, ...]:
    """Descriptive per-year support; annual eligibility itself belongs to the engine."""
    by_year: dict[int, list[MonthlySoilMoisture]] = defaultdict(list)
    for record in series.months:
        by_year[record.month.year].append(record)
    result = []
    for year in sorted(by_year):
        records = by_year[year]
        missing = tuple(
            (r.month.month, r.inference_exclusion_reasons[0])
            for r in records if not r.usable_for_inference
        )
        result.append(YearSupport(
            year=year,
            is_complete_calendar_year=len(records) == 12,
            requested_months=len(records),
            usable_months=len(records) - len(missing),
            missing_months=missing,
        ))
    return tuple(result)


def annual_policy(descriptor: DatasetDescriptor) -> AnnualAggregationPolicy:
    """Soil moisture annual rule: 12 of 12 usable months in a complete calendar year.

    Soil moisture has a strong seasonal cycle, so a missing wet or dry month would
    bias the annual mean. Project policy, not a universal standard.
    """
    if descriptor.variable != "soil_moisture":
        raise ValueError("annual policy requested for a non-soil-moisture dataset")
    return AnnualAggregationPolicy(
        minimum_represented_months=12,
        minimum_valid_slot_coverage=1.0,
        require_all_quarters=True,
        exclude_partial_calendar_years_from_inference=True,
    )


def _require_same_dataset(series: MonthlySoilMoistureSeries, descriptor: DatasetDescriptor) -> None:
    if series.dataset_key != descriptor.key:
        raise ValueError(
            f"series for {series.dataset_key!r} does not belong to dataset {descriptor.key!r}"
        )


def to_observation_series(
    series: MonthlySoilMoistureSeries,
    descriptor: DatasetDescriptor,
    *,
    derived_volumetric: bool = False,
) -> ObservationSeries:
    """Map one dataset's monthly records onto the shared engine's input model.

    Each requested month is an expected slot; months with images are available;
    only months usable for inference become observations. Support is a native grid
    cell, so pixel-count fields stay ``None``.
    """
    _require_same_dataset(series, descriptor)
    if derived_volumetric and not descriptor.supports_derived_volumetric:
        raise ValueError(f"{descriptor.key} has no derived volumetric representation")

    by_year: dict[int, list[MonthlySoilMoisture]] = defaultdict(list)
    for record in series.months:
        by_year[record.month.year].append(record)

    coverage = tuple(
        YearCoverage(
            year=year,
            expected_slot_dates=tuple(r.month for r in records),
            available_image_dates=tuple(r.month for r in records if r.available_images > 0),
            is_complete_calendar_year=len(records) == 12,
        )
        for year, records in sorted(by_year.items())
    )
    observations = tuple(
        TimedValue(
            date=r.month,
            value=r.derived_volumetric if derived_volumetric else r.mean_native,
        )
        for r in series.months
        if r.usable_for_inference
    )
    return ObservationSeries(
        variable="soil_moisture",
        value_units="m3 m-3" if derived_volumetric else descriptor.native_units,
        dataset=descriptor.key,
        observations=observations,
        coverage_by_year=coverage,
    )


def analyze_series(
    series: MonthlySoilMoistureSeries,
    descriptor: DatasetDescriptor,
    trend_policy: TrendPolicy,
) -> SoilMoistureAnalysis:
    """Run the unchanged shared engine on one dataset's monthly series."""
    _require_same_dataset(series, descriptor)
    policy = annual_policy(descriptor)

    def run(derived: bool):
        obs = to_observation_series(series, descriptor, derived_volumetric=derived)
        summaries = aggregate_annual(obs, policy)
        return summaries, analyze_trend(summaries, obs.value_units, trend_policy)

    summaries, trend = run(False)
    derived_summaries = derived_trend = None
    if descriptor.supports_derived_volumetric:
        derived_summaries, derived_trend = run(True)

    return SoilMoistureAnalysis(
        dataset_key=descriptor.key,
        collection_id=descriptor.collection_ids[0],
        version=descriptor.version,
        product_type=descriptor.product_type,
        quantity_kind=descriptor.quantity_kind,
        units=descriptor.native_units,
        depth_top_cm=descriptor.depth_top_cm,
        depth_bottom_cm=descriptor.depth_bottom_cm,
        depth_semantics=descriptor.depth_semantics,
        value_definition=_VALUE_DEFINITIONS[descriptor.is_model],
        annual_aggregation="equal-weight mean of monthly means",
        monthly=series,
        year_support=year_support(series),
        annual_summaries=summaries,
        trend=trend,
        derived_units="m3 m-3" if descriptor.supports_derived_volumetric else None,
        derived_annual_summaries=derived_summaries,
        derived_trend=derived_trend,
        support_policy_status=SupportPolicy.status,
        thresholds_are_universal_standards=SupportPolicy.is_universal_standard,
    )
