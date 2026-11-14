"""Descriptive ordinary least squares (OLS) line for the Statistical Methods Lab.

OLS is reported only as a descriptive comparison with the project's Theil–Sen slope.
No p-value or conventional confidence interval is computed: those need assumptions
(independent, normally distributed residuals with constant variance) that annual
environmental series often violate.

X is the actual calendar year (gaps preserved), never an array position. The slope uses
centred sums with math.fsum for numerical stability; the intercept is at year 0 so it is
directly comparable with the Theil–Sen intercept returned by the trend engine.
"""

from dataclasses import dataclass
from math import fsum, isfinite


@dataclass(frozen=True)
class OLSResult:
    available: bool
    n: int
    slope: float | None
    intercept: float | None
    r_squared: float | None
    residuals: tuple[tuple[int, float], ...]
    unavailable_reason: str | None
    r_squared_unavailable_reason: str | None


def ols_line(years: list[int], values: list[float], minimum_points: int = 3) -> OLSResult:
    """Fit value = intercept + slope * year by least squares on the given observations."""
    if len(years) != len(values):
        raise ValueError("years and values must have the same length")
    if len(set(years)) != len(years):
        raise ValueError("years must be unique")
    if any(not isfinite(v) for v in values) or any(not isinstance(y, int) for y in years):
        raise ValueError("observations must be finite and years must be integers")
    n = len(years)
    if n < minimum_points:
        return OLSResult(False, n, None, None, None, (), f"At least {minimum_points} eligible observations are required", None)
    xm = fsum(years) / n
    ym = fsum(values) / n
    sxx = fsum((x - xm) ** 2 for x in years)
    sxy = fsum((x - xm) * (y - ym) for x, y in zip(years, values))
    slope = sxy / sxx  # sxx > 0 because years are unique and n >= 2
    intercept = ym - slope * xm
    residuals = tuple((x, y - (intercept + slope * x)) for x, y in zip(years, values))
    sst = fsum((y - ym) ** 2 for y in values)
    if sst == 0:
        return OLSResult(True, n, slope, intercept, None, residuals, None, "R² is undefined for a constant series")
    ssr = fsum(r * r for _, r in residuals)
    return OLSResult(True, n, slope, intercept, max(0.0, 1 - ssr / sst), residuals, None, None)
