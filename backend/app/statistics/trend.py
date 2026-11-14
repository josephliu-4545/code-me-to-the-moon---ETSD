from math import erf, isfinite, sqrt

from scipy.stats import spearmanr, theilslopes

from app.statistics.models import (
    AnnualSummary,
    MannKendallResult,
    SerialDependenceResult,
    TheilSenResult,
    TrendAnalysisResult,
)
from app.statistics.policies import TrendPolicy


def _normal_two_sided_p(z: float) -> float:
    return 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))


def _mann_kendall(values: list[float], alpha: float) -> MannKendallResult | None:
    n = len(values)
    s = sum(
        (values[j] > values[i]) - (values[j] < values[i])
        for i in range(n - 1)
        for j in range(i + 1, n)
    )
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    tie_term = sum(count * (count - 1) * (2 * count + 5) for count in counts.values())
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18
    if variance <= 0:
        return None
    if s > 0:
        z = (s - 1) / sqrt(variance)
    elif s < 0:
        z = (s + 1) / sqrt(variance)
    else:
        z = 0.0
    p_value = _normal_two_sided_p(z)
    pair_count = n * (n - 1) / 2
    tied_value_pairs = sum(count * (count - 1) / 2 for count in counts.values())
    tau_denominator = sqrt(pair_count * (pair_count - tied_value_pairs))
    tau = s / tau_denominator
    significant = p_value < alpha
    direction = "no_detected_trend"
    if significant and s > 0:
        direction = "increasing"
    elif significant and s < 0:
        direction = "decreasing"
    return MannKendallResult(
        s=s,
        variance=variance,
        z=z,
        tau=tau,
        p_value=p_value,
        alpha=alpha,
        alternative="two-sided",
        is_statistically_significant=significant,
        direction=direction,
    )


def _dependence(
    years: list[int],
    residuals: list[float],
    policy: TrendPolicy,
) -> SerialDependenceResult:
    pairs = [
        (residuals[index], residuals[index + 1])
        for index in range(len(years) - 1)
        if years[index + 1] - years[index] == 1
    ]
    caveat = (
        "Failure to detect lag-1 autocorrelation does not prove independence; "
        "the diagnostic may have low power."
    )
    if len(pairs) < policy.minimum_adjacent_residual_pairs:
        return SerialDependenceResult(
            len(pairs), None, None, "insufficient_adjacent_pairs", caveat, False,
            "Too few adjacent annual residual pairs",
        )
    left, right = zip(*pairs)
    if len(set(left)) == 1 or len(set(right)) == 1:
        return SerialDependenceResult(
            len(pairs), None, None, "undefined", caveat, False,
            "Lag-1 diagnostic is undefined for constant residuals",
        )
    result = spearmanr(left, right)
    rho, p_value = float(result.statistic), float(result.pvalue)
    if not isfinite(rho) or not isfinite(p_value):
        return SerialDependenceResult(
            len(pairs), None, None, "undefined", caveat, False,
            "Lag-1 diagnostic returned a non-finite result",
        )
    material = abs(rho) >= policy.material_lag1_rho or p_value < policy.alpha
    return SerialDependenceResult(
        adjacent_pair_count=len(pairs),
        lag1_spearman_rho=rho,
        diagnostic_p_value=p_value,
        status="material_dependence_detected" if material else "not_detected_with_caveat",
        caveat=caveat,
        supported_for_standard_inference=not material,
        unavailable_reason="Material lag-1 serial dependence detected" if material else None,
    )


def analyze_trend(
    summaries: tuple[AnnualSummary, ...],
    value_units: str,
    policy: TrendPolicy,
) -> TrendAnalysisResult:
    eligible = [
        item for item in summaries
        if item.eligible_for_trend_inference and item.annual_value is not None
    ]
    eligible.sort(key=lambda item: item.year)
    years = [item.year for item in eligible]
    values = [float(item.annual_value) for item in eligible]
    excluded = tuple(
        (item.year, item.eligibility_reasons)
        for item in summaries
        if item not in eligible
    )
    missing = tuple(
        year for year in range(min(years), max(years) + 1) if year not in years
    ) if years else ()
    if len(eligible) < policy.minimum_slope_years:
        reason = f"At least {policy.minimum_slope_years} eligible annual observations are required"
        return TrendAnalysisResult(
            "annual_summaries_only", tuple(years), excluded, missing,
            None, None, None, reason, reason,
        )

    slope_result = theilslopes(values, x=years, alpha=0.95, method="separate")
    base_theil = TheilSenResult(
        slope=float(slope_result.slope),
        intercept=float(slope_result.intercept),
        slope_units=f"{value_units}/year",
        confidence_interval=None,
        confidence_interval_unavailable_reason="Inferential confidence interval not supported",
    )
    if len(eligible) < policy.minimum_significance_years:
        reason = f"At least {policy.minimum_significance_years} eligible annual observations are required"
        return TrendAnalysisResult(
            "descriptive_slope", tuple(years), excluded, missing,
            base_theil, None, None, None, reason,
        )
    if len(set(values)) == 1:
        reason = "All eligible annual observations are identical; inferential variance is degenerate"
        return TrendAnalysisResult(
            "descriptive_slope", tuple(years), excluded, missing,
            base_theil, None, None, None, reason,
        )

    residuals = [
        value - (float(slope_result.intercept) + float(slope_result.slope) * year)
        for year, value in zip(years, values, strict=True)
    ]
    serial = _dependence(years, residuals, policy)
    if not serial.supported_for_standard_inference:
        return TrendAnalysisResult(
            "descriptive_slope", tuple(years), excluded, missing,
            base_theil, serial, None, None, serial.unavailable_reason,
        )

    mk = _mann_kendall(values, policy.alpha)
    if mk is None:
        reason = "Mann-Kendall variance is degenerate"
        return TrendAnalysisResult(
            "descriptive_slope", tuple(years), excluded, missing,
            base_theil, serial, None, None, reason,
        )
    ci = (float(slope_result.low_slope), float(slope_result.high_slope))
    supported_theil = TheilSenResult(
        slope=base_theil.slope,
        intercept=base_theil.intercept,
        slope_units=base_theil.slope_units,
        confidence_interval=ci if all(isfinite(value) for value in ci) else None,
        confidence_interval_unavailable_reason=None if all(isfinite(value) for value in ci) else "Non-finite interval",
    )
    return TrendAnalysisResult(
        "statistical_inference", tuple(years), excluded, missing,
        supported_theil, serial, mk, None, None,
    )

