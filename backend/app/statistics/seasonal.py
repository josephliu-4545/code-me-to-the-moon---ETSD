"""Seasonal Kendall test and seasonal Sen slope on monthly values (Hirsch, Slack & Smith 1982).

Each calendar month is a season. Mann-Kendall S and its tie-corrected variance are computed
within each month across years and summed; the slope is the median of all within-month
pairwise slopes. Months missing in some years (e.g. monsoon cloud) simply contribute fewer
pairs, so no complete calendar year is required.

Not applied: the Hirsch-Slack (1984) correction for correlation between seasons. With about
ten years it is unreliable, so the limitation is disclosed instead.
"""

from math import ceil, floor, isfinite, sqrt
from statistics import NormalDist, median

from app.statistics.models import MannKendallResult, TheilSenResult, TrendAnalysisResult
from app.statistics.policies import TrendPolicy
from app.statistics.trend import _normal_two_sided_p

LIMITATION = (
    "Seasonal Kendall treats months as independent; correlation between adjacent months "
    "(Hirsch-Slack correction) is not applied, so the p-value may be optimistic."
)


def _season_stats(points: list[tuple[int, float]]) -> tuple[int, float, float, list[float]]:
    """Return S, tie-corrected variance, pair count and pairwise slopes for one month."""
    n = len(points)
    s, slopes = 0, []
    for i in range(n - 1):
        for j in range(i + 1, n):
            (yi, vi), (yj, vj) = points[i], points[j]
            s += (vj > vi) - (vj < vi)
            slopes.append((vj - vi) / (yj - yi))
    counts: dict[float, int] = {}
    for _, value in points:
        counts[value] = counts.get(value, 0) + 1
    ties = sum(c * (c - 1) * (2 * c + 5) for c in counts.values())
    variance = (n * (n - 1) * (2 * n + 5) - ties) / 18
    return s, variance, n * (n - 1) / 2, slopes


def deseasonalized_ols_slope(monthly: dict[tuple[int, int], float], months: list[int]) -> float | None:
    """OLS slope per year of monthly anomalies (value minus that month's mean), used months only."""
    groups: dict[int, list[tuple[int, float]]] = {}
    for (year, month), value in monthly.items():
        if month in months and value is not None:
            groups.setdefault(month, []).append((year, value))
    xs, ys = [], []
    for month, pts in groups.items():
        mean = sum(v for _, v in pts) / len(pts)
        xs += [year + (month - 0.5) / 12 for year, _ in pts]
        ys += [v - mean for _, v in pts]
    if len(set(xs)) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def seasonal_trend(
    monthly: dict[tuple[int, int], float],
    first_year: int,
    last_year: int,
    units: str,
    policy: TrendPolicy,
    minimum_month_year_fraction: float = 0.7,
) -> tuple[TrendAnalysisResult, list[int]]:
    """Analyze {(year, month): value}. Returns the trend and the months used.

    A month is used only if it has values in at least `minimum_month_year_fraction` of the
    years in [first_year, last_year] and in at least `policy.minimum_slope_years` years.
    """
    span = last_year - first_year + 1
    needed = max(policy.minimum_slope_years, ceil(minimum_month_year_fraction * span))
    by_month: dict[int, list[tuple[int, float]]] = {}
    for (year, month), value in sorted(monthly.items()):
        if first_year <= year <= last_year and value is not None and isfinite(value):
            by_month.setdefault(month, []).append((year, float(value)))
    used = {m: pts for m, pts in by_month.items() if len(pts) >= needed}
    months = sorted(used)
    years = sorted({y for pts in used.values() for y, _ in pts})
    excluded = ()  # per-month exclusion is reported through the returned months list

    if not months:
        reason = f"No calendar month has data in at least {needed} of {span} years"
        return TrendAnalysisResult("annual_summaries_only", (), excluded, (), None, None, None, reason, reason), []

    s_total, var_total, pairs_total, slopes = 0, 0.0, 0.0, []
    for m in months:
        s, var, pairs, sl = _season_stats(used[m])
        s_total, var_total, pairs_total = s_total + s, var_total + var, pairs_total + pairs
        slopes.extend(sl)
    slope = median(slopes)
    values = [v for pts in used.values() for _, v in pts]
    mid_year = (years[0] + years[-1]) / 2
    # Level line through the mean of used monthly values at mid-period (seasonal cycle removed).
    intercept = sum(values) / len(values) - slope * mid_year
    descriptive = TheilSenResult(slope, intercept, f"{units}/year", None, "Inferential confidence interval not supported")

    if len(years) < policy.minimum_significance_years:
        reason = f"At least {policy.minimum_significance_years} years are required for significance"
        return TrendAnalysisResult("descriptive_slope", tuple(years), excluded, (), descriptive, None, None, None, reason), months
    if var_total <= 0:
        reason = "Seasonal Kendall variance is degenerate"
        return TrendAnalysisResult("descriptive_slope", tuple(years), excluded, (), descriptive, None, None, None, reason), months

    z = 0.0 if s_total == 0 else (s_total - (1 if s_total > 0 else -1)) / sqrt(var_total)
    p_value = _normal_two_sided_p(z)
    significant = p_value < policy.alpha
    direction = ("increasing" if s_total > 0 else "decreasing") if significant else "no_detected_trend"
    mk = MannKendallResult(s_total, var_total, z, s_total / pairs_total, p_value, policy.alpha, "two-sided", significant, direction)

    # Rank-based CI for the seasonal Sen slope (Hirsch et al. 1982, Gilbert 1987 §17.5).
    slopes.sort()
    c = NormalDist().inv_cdf(1 - policy.alpha / 2) * sqrt(var_total)
    lower, upper = floor((len(slopes) - c) / 2), floor((len(slopes) + c) / 2) + 1
    ci = (slopes[lower - 1], slopes[upper - 1]) if 1 <= lower and upper <= len(slopes) else None
    theil = TheilSenResult(slope, intercept, f"{units}/year", ci, None if ci else "Too few slopes for a confidence interval")
    return TrendAnalysisResult("statistical_inference", tuple(years), excluded, (), theil, None, mk, None, None), months
