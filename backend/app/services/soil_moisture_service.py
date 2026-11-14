"""Soil moisture orchestration: one dataset at a time, plus descriptive comparison.

Datasets and SMAP versions are never merged, averaged or gap-filled from each other.
Comparison is descriptive only (decision D7).
"""

from dataclasses import dataclass
from datetime import date
from statistics import mean

from scipy.stats import spearmanr

from app.services.soil_moisture_provider import (
    EarthEngineSoilMoistureProvider,
    ProviderResult,
    SoilMoistureRetrievalError,
)
from app.soil_moisture.aggregation import analyze_series, assess_months
from app.soil_moisture.datasets import DatasetDescriptor, get_dataset
from app.soil_moisture.models import MonthStatus, SoilMoistureAnalysis, SupportPolicy
from app.statistics.policies import TrendPolicy


AGRMET_SHIFT_YEAR = 2011
GALWEM_SWITCH = date(2025, 6, 9)


@dataclass(frozen=True)
class SoilMoistureResult:
    descriptor: DatasetDescriptor
    analysis: SoilMoistureAnalysis
    provider: ProviderResult
    latitude: float
    longitude: float
    start: date
    end: date
    cell_status: str
    coastal_proximity: bool | None
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class PairComparison:
    datasets: tuple[str, str]
    common_valid_months: int
    mean_difference_m3_m3: float | None
    monthly_anomaly_spearman_rho: float | None
    unavailable_reasons: tuple[str, ...]


@dataclass(frozen=True)
class SoilMoistureComparison:
    results: tuple[SoilMoistureResult, ...]
    common_eligible_years: tuple[int, ...]
    slope_sign_agreement: bool | None
    pairs: tuple[PairComparison, ...]
    excluded_frozen_months: int
    differences: tuple[str, ...]


def _volumetric_by_month(result: SoilMoistureResult) -> dict[date, float]:
    frozen = set(result.provider.frozen_months)
    out = {}
    for r in result.analysis.monthly.months:
        if not r.usable_for_inference or r.month in frozen:
            continue
        value = r.derived_volumetric if result.descriptor.supports_derived_volumetric else r.mean_native
        if value is not None:
            out[r.month] = value
    return out


def _anomalies(values: dict[date, float], months: list[date]) -> list[float]:
    by_calendar: dict[int, list[float]] = {}
    for m in months:
        by_calendar.setdefault(m.month, []).append(values[m])
    climatology = {k: mean(v) for k, v in by_calendar.items()}
    return [values[m] - climatology[m.month] for m in months]


class SoilMoistureService:
    def __init__(
        self,
        provider: EarthEngineSoilMoistureProvider,
        support_policy: SupportPolicy | None = None,
        trend_policy: TrendPolicy | None = None,
        compare_min_overlap_months: int = 36,
    ) -> None:
        self._provider = provider
        self._policy = support_policy or SupportPolicy()
        self._trend_policy = trend_policy or TrendPolicy()
        self._min_overlap = compare_min_overlap_months

    @property
    def support_policy(self) -> SupportPolicy:
        return self._policy

    @property
    def trend_policy(self) -> TrendPolicy:
        return self._trend_policy

    def availability(self, key: str):
        return self._provider.availability(get_dataset(key))

    def analyze(self, key: str, latitude: float, longitude: float, start: date, end: date) -> SoilMoistureResult:
        descriptor = get_dataset(key)
        fetched = self._provider.fetch(descriptor, latitude, longitude, start, end)
        try:
            series = assess_months(descriptor, fetched.samples, fetched.availability, start, end, self._policy)
        except ValueError as exc:  # physically invalid provider values
            raise SoilMoistureRetrievalError(str(exc)) from exc
        analysis = analyze_series(series, descriptor, self._trend_policy)

        in_catalog = [r for r in series.months if r.status is not MonthStatus.OUTSIDE_AVAILABILITY]
        with_images = [r for r in in_catalog if r.available_images > 0]
        if not in_catalog:
            cell_status = "outside_catalog_availability"
        elif with_images and all(r.valid_values == 0 for r in with_images):
            cell_status = "no_valid_land_values"
        else:
            cell_status = "ok"
        coastal = None if fetched.valid_cells_in_3x3 is None else fetched.valid_cells_in_3x3 < 9
        return SoilMoistureResult(
            descriptor, analysis, fetched, latitude, longitude, start, end, cell_status, coastal,
            self._limitations(descriptor, fetched, start, end, cell_status, coastal),
        )

    def compare(self, keys: tuple[str, ...], latitude: float, longitude: float,
                start: date, end: date) -> SoilMoistureComparison:
        if not 2 <= len(keys) <= 3 or len(set(keys)) != len(keys):
            raise ValueError("compare requires 2 or 3 distinct datasets")
        results = tuple(self.analyze(k, latitude, longitude, start, end) for k in keys)

        eligible = [
            {s.year for s in r.analysis.annual_summaries if s.eligible_for_trend_inference} for r in results
        ]
        common_years = tuple(sorted(set.intersection(*eligible)))
        slopes = [r.analysis.trend.theil_sen.slope if r.analysis.trend.theil_sen else None for r in results]
        sign_agreement = None
        if all(s is not None for s in slopes):
            signs = {(s > 0) - (s < 0) for s in slopes}
            sign_agreement = len(signs) == 1

        volumetric = [_volumetric_by_month(r) for r in results]
        frozen_excluded = sum(
            1 for r in results for x in r.analysis.monthly.months
            if x.usable_for_inference and x.month in set(r.provider.frozen_months)
        )
        pairs = []
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a, b = volumetric[i], volumetric[j]
                common = sorted(set(a) & set(b))
                reasons = []
                diff = rho = None
                if common:
                    diff = mean(a[m] - b[m] for m in common)
                else:
                    reasons.append("no_common_valid_months")
                if len(common) >= self._min_overlap:
                    stat = spearmanr(_anomalies(a, common), _anomalies(b, common)).statistic
                    rho = float(stat) if stat == stat else None
                    if rho is None:
                        reasons.append("anomaly_correlation_undefined")
                else:
                    reasons.append("insufficient_overlap_months")
                pairs.append(PairComparison((keys[i], keys[j]), len(common), diff, rho, tuple(reasons)))

        differences = []
        descs = [r.descriptor for r in results]
        if len({(d.depth_top_cm, d.depth_bottom_cm, d.depth_semantics) for d in descs}) > 1:
            differences.append("depth: 0-10 cm model layer vs approximately 0-5 cm satellite sensing depth")
        if len({d.quantity_kind for d in descs}) > 1:
            differences.append("quantity: layer water storage (converted to a layer-mean m3 m-3) vs retrieved volumetric content")
        if len({d.native_grid for d in descs}) > 1:
            differences.append("footprint: 0.25 degree vs 9 km grid cell")
        if len({d.product_type for d in descs}) > 1:
            differences.append("method: open-loop land surface model vs satellite retrieval")
            differences.append("sampling: 8 instantaneous model states per day vs one 06:00 overpass when retrieved")
        if len({d.collection_ids for d in descs if d.is_satellite}) > 1:
            differences.append("version: SMAP Version 005 and Version 006 use different processing; they are compared, never merged")
        return SoilMoistureComparison(results, common_years, sign_agreement, tuple(pairs),
                                      frozen_excluded, tuple(differences))

    @staticmethod
    def _limitations(descriptor, fetched: ProviderResult, start: date, end: date,
                     cell_status: str, coastal: bool | None) -> tuple[str, ...]:
        leading: list[str] = []
        notes = list(descriptor.limitations)
        if cell_status == "no_valid_land_values":
            leading.append((
                "The grid cell containing this point has no valid values in this period. It may be "
                "water, coast, ice, urban, or (for SMAP) persistently unretrievable. No neighbouring "
                "cell was substituted."))
        if coastal:
            notes.append(
                f"Only {fetched.valid_cells_in_3x3} of the 9 surrounding native cells hold data; the sampled "
                "cell may be partly water or near a mask edge. Values were not altered or substituted.")
        if descriptor.is_model:
            if start.year <= AGRMET_SHIFT_YEAR < end.year:
                notes.append("This period spans the post-2011 AGRMET forcing shift; part of any trend may be artificial.")
            if start <= GALWEM_SWITCH < end:
                notes.append("This period spans the 2025-06-09 switch to GALWEM radiation forcing; part of any trend may be artificial.")
            if fetched.frozen_months:
                notes.append(
                    f"{len(fetched.frozen_months)} month(s) had a mean 0-10 cm soil temperature below 0 C; "
                    "values may include frozen water (unverified) and are excluded from dataset comparison.")
        else:
            d = fetched.diagnostics
            rejected, valid = d.get("qc_rejected_retrievals", 0), d.get("valid_retrievals", 0)
            if rejected and rejected >= valid:
                leading.append((
                    f"{rejected} of {rejected + valid} SMAP retrievals at this cell failed the recommended-quality "
                    "flag (for example urban, water, dense vegetation, frozen ground or interference); "
                    "only quality-passing retrievals are used."))
            if d.get("fill_value_leaks"):
                notes.append(f"{d['fill_value_leaks']} fill-value sentinel(s) appeared in the data and were excluded (provider anomaly).")
        return tuple(leading + notes)
