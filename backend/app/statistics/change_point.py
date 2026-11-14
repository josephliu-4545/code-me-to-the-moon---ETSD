"""Flag a sudden step in a yearly series (e.g. a data-source change) with the Pettitt test.

Pettitt (1979) finds the most likely single shift point and its approximate p-value. It is
also significant for a smooth monotonic trend, so a step is reported only when a two-mean
step model also fits better than a straight line (lower residual sum of squares).
"""

from math import exp


def pettitt(values: list[float]) -> tuple[int, int, float]:
    """Return (k, K, p): the shift is after values[k], K = max |U_t|, approximate two-sided p."""
    n = len(values)
    best_k, best_u, u = 0, 0, 0
    for t in range(n - 1):
        # U_t = U_{t-1} + sum_j sign(x_t - x_j) over all j
        u += sum((values[t] > x) - (values[t] < x) for x in values)
        if abs(u) > best_u:
            best_k, best_u = t, abs(u)
    p = min(1.0, 2 * exp(-6 * best_u**2 / (n**3 + n**2)))
    return best_k, best_u, p


def _rss(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values)


def detect_step(years: list[int], values: list[float], alpha: float = 0.05, minimum_years: int = 8) -> dict:
    """Describe whether `values` (one per year, sorted) contain a sudden step."""
    if len(values) < minimum_years:
        return {"status": "not_tested", "reason": f"At least {minimum_years} years are required"}
    k, _, p = pettitt(values)
    before, after = values[: k + 1], values[k + 1 :]
    n = len(values)
    xm, ym = sum(years) / n, sum(values) / n
    sxx = sum((x - xm) ** 2 for x in years)
    slope = sum((x - xm) * (y - ym) for x, y in zip(years, values)) / sxx
    linear_rss = sum((y - (ym + slope * (x - xm))) ** 2 for x, y in zip(years, values))
    step_rss = _rss(before) + _rss(after)
    detected = p < alpha and step_rss < linear_rss
    return {
        "status": "step_detected" if detected else "none",
        "last_year_before": years[k],
        "first_year_after": years[k + 1],
        "mean_before": sum(before) / len(before),
        "mean_after": sum(after) / len(after),
        "shift": sum(after) / len(after) - sum(before) / len(before),
        "pettitt_p_value": p,
        "step_fits_better_than_line": step_rss < linear_rss,
    }
