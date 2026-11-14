from dataclasses import dataclass
from datetime import date
from math import ceil

import numpy as np

from app.statistics.models import TimedValue


@dataclass(frozen=True)
class HotDayPolicy:
    reference_start_year: int = 1991
    reference_end_year: int = 2020
    percentile: float = .90
    window_days: int = 5
    minimum_window_fraction: float = .75
    bootstrap_repetitions: int = 200
    random_seed: int = 20201112
    maximum_missing_days_per_year: int = 15
    maximum_missing_days_per_month: int = 3


@dataclass(frozen=True)
class HotDayThresholdSet:
    values: dict[int, float | None]
    sample_counts: dict[int, int]
    quantile_method: str = "Hyndman-Fan type 8"


@dataclass(frozen=True)
class HotDayClassification:
    date: date
    temperature_celsius: float
    threshold: float | None
    is_hot_day: bool | None


@dataclass(frozen=True)
class BootstrapFrequency:
    year: int
    raw_count: int
    valid_days: int
    adjusted_percentage: float
    confidence_interval: tuple[float, float]
    repetitions: int


def _noleap_doy(day: date) -> int | None:
    if day.month == 2 and day.day == 29: return None
    return date(2001, day.month, day.day).timetuple().tm_yday


def build_thresholds(observations: tuple[TimedValue, ...], policy: HotDayPolicy) -> HotDayThresholdSet:
    grouped={day:[] for day in range(1,366)}
    for item in observations:
        doy=_noleap_doy(item.date)
        if doy is not None: grouped[doy].append(item.value)
    expected_years=policy.reference_end_year-policy.reference_start_year+1
    minimum=ceil(expected_years*policy.window_days*policy.minimum_window_fraction)
    values={}; counts={}; half=policy.window_days//2
    for target in range(1,366):
        sample=[]
        for offset in range(-half,half+1):
            day=((target-1+offset)%365)+1; sample.extend(grouped[day])
        counts[target]=len(sample)
        values[target]=float(np.quantile(sample,policy.percentile,method="median_unbiased")) if len(sample)>=minimum else None
    return HotDayThresholdSet(values,counts)


def classify_year(observations: tuple[TimedValue, ...], thresholds: HotDayThresholdSet) -> tuple[HotDayClassification, ...]:
    result=[]
    for item in sorted(observations,key=lambda x:x.date):
        doy=_noleap_doy(item.date)
        if doy is None:
            left,right=thresholds.values[59],thresholds.values[60]
            threshold=(left+right)/2 if left is not None and right is not None else None
        else: threshold=thresholds.values[doy]
        result.append(HotDayClassification(item.date,item.value,threshold,None if threshold is None else item.value>threshold))
    return tuple(result)


def bootstrap_base_year(reference: tuple[TimedValue, ...], year: int, policy: HotDayPolicy) -> BootstrapFrequency:
    target=tuple(x for x in reference if x.date.year==year)
    full=build_thresholds(reference,policy); raw=classify_year(target,full)
    raw_count=sum(x.is_hot_day is True for x in raw)
    other_years=[y for y in range(policy.reference_start_year,policy.reference_end_year+1) if y != year]
    by_year={y:tuple(x for x in reference if x.date.year==y) for y in other_years}
    if not target or any(not by_year[y] for y in other_years): raise ValueError("complete reference years are required for bootstrap")
    percentages=[]; others=tuple(x for x in reference if x.date.year != year)
    for replacement_year in other_years:
        replacement=by_year[replacement_year]
        thresholds=build_thresholds(others+replacement,policy)
        classified=classify_year(target,thresholds); valid=[x for x in classified if x.is_hot_day is not None]
        percentages.append(100*sum(x.is_hot_day is True for x in valid)/len(valid))
    return BootstrapFrequency(year,raw_count,len(target),float(np.mean(percentages)),(float(np.quantile(percentages,.025)),float(np.quantile(percentages,.975))),len(other_years))
