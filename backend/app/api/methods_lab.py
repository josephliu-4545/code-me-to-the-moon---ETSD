"""Statistical Methods Lab block for the /api/v2 analysis envelope.

Built from the observations and results the analysis already produced: no new NASA
retrieval, no new significance procedure, and no change to Theil–Sen, Mann–Kendall,
the dependence screen, the seasonal method or the change-point check. The only new
statistic is a descriptive OLS line (app.statistics.ols), computed on exactly the same
eligible observations as the existing trend so the two estimators can be compared.
"""

import calendar
from math import isfinite
from typing import Any

from app.statistics.ols import ols_line
from app.statistics.policies import TrendPolicy
from app.statistics.seasonal import deseasonalized_ols_slope


METHODS = {
    "ols": {
        "name": "Ordinary least squares (descriptive)",
        "definition": "Slope b and intercept a minimising Σ(yᵢ − a − b·xᵢ)², with x = calendar year and y = eligible annual value; b = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)².",
        "role": "Descriptive comparison only. No p-value or confidence interval is reported because they require independent, normally distributed, constant-variance residuals.",
    },
    "theil_sen": {
        "name": "Theil–Sen estimator",
        "definition": "Median of the slopes (yⱼ − yᵢ)/(xⱼ − xᵢ) over all pairs of eligible years (SciPy theilslopes, method='separate').",
        "role": "The project's trend estimator; robust to outliers.",
    },
    "mann_kendall": {
        "name": "Mann–Kendall trend test",
        "definition": "S = Σ_{i<j} sign(yⱼ − yᵢ); tie-corrected variance; continuity-corrected Z; two-sided p-value; Kendall τ = S / √(n₀(n₀ − n₁)), where n₀ = n(n − 1)/2 is the number of pairs and n₁ = Σ t(t − 1)/2 counts pairs tied in value (tie-adjusted τ-b; years never tie).",
        "role": "Tests for evidence of a monotonic trend; reported only after the lag-1 dependence screen and with enough eligible years.",
    },
    "serial_dependence": {
        "name": "Lag-1 residual dependence screen",
        "definition": "Spearman correlation between consecutive Theil–Sen residuals (adjacent years only).",
        "role": "Withholds standard significance when material dependence is detected.",
    },
    "seasonal_kendall": {
        "name": "Seasonal Kendall test and seasonal Sen slope",
        "definition": "Mann–Kendall S and variance computed within each calendar month across years and summed; τ = summed S / total number of within-month pairs (no tie adjustment); slope = median of all within-month pairwise slopes (Hirsch, Slack & Smith 1982).",
        "role": "Used for NDVI, where cloud gaps leave few complete years.",
    },
    "deseasonalized_ols": {
        "name": "Deseasonalized OLS (descriptive)",
        "definition": "OLS slope of monthly anomalies (value minus that calendar month's mean) against decimal year, using the same months and years as the seasonal Sen slope.",
        "role": "Descriptive comparison with the seasonal Sen slope on the same monthly observations.",
    },
    "change_point": {
        "name": "Pettitt change-point check",
        "definition": "Pettitt (1979) statistic for the most likely single shift; a step is reported only if p < α and a two-mean step model fits better than a straight line.",
        "role": "Flags abrupt shifts (for example data-source changes) that a gradual trend line would misrepresent.",
    },
}


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)


def _annual_block(annual: list[dict[str, Any]], trend: dict[str, Any] | None, policy: TrendPolicy) -> dict[str, Any]:
    eligible_years = sorted(trend.get("eligible_years", [])) if trend else []
    by_year = {a["year"]: a for a in annual}
    eligible = [{"year": y, "value": by_year[y]["value"]} for y in eligible_years if y in by_year]
    excluded = [{"year": a["year"], "value": a["value"] if _finite(a["value"]) else None, "reasons": a.get("reasons", [])}
                for a in annual if a["year"] not in set(eligible_years)]
    out: dict[str, Any] = {"observations": {"basis": "eligible annual values (the observations the trend used)",
                                            "eligible": eligible, "excluded": excluded}}
    if len(eligible) != len(eligible_years) or not all(_finite(e["value"]) for e in eligible):
        out["unavailable"] = "The eligible annual values could not be matched to the trend's eligible years, so no comparison is shown."
        return out
    years = [e["year"] for e in eligible]
    values = [float(e["value"]) for e in eligible]
    ols = ols_line(years, values, policy.minimum_slope_years)
    ts_slope, ts_int = (trend or {}).get("slope"), (trend or {}).get("intercept")
    out["ols"] = {
        "available": ols.available, "n": ols.n, "slope": ols.slope, "intercept": ols.intercept,
        "r_squared": ols.r_squared, "r_squared_unavailable_reason": ols.r_squared_unavailable_reason,
        "residuals": [{"year": y, "residual": r} for y, r in ols.residuals],
        "unavailable_reason": ols.unavailable_reason, "slope_units": (trend or {}).get("slope_units"),
        "inference": None, "inference_note": METHODS["ols"]["role"],
    }
    out["theil_sen"] = {
        "available": ts_slope is not None, "n": len(years), "slope": ts_slope, "intercept": ts_int,
        "slope_units": (trend or {}).get("slope_units"),
        "confidence_interval": (trend or {}).get("confidence_interval"),
        "confidence_interval_unavailable_reason": (trend or {}).get("confidence_interval_unavailable_reason"),
        "unavailable_reason": None if ts_slope is not None else (trend or {}).get("slope_unavailable_reason"),
        "source": "existing trend engine (unchanged)",
    }
    if ols.available and ts_slope is not None:
        out["comparison"] = {
            "same_observations": True,
            "n": len(years),
            "slope_difference": ols.slope - ts_slope,  # OLS minus Theil–Sen
            "slope_units": (trend or {}).get("slope_units"),
            "fitted": [{"year": y, "observed": v, "ols": ols.intercept + ols.slope * y, "theil_sen": ts_int + ts_slope * y}
                       for y, v in zip(years, values)],
            "fit_range": [years[0], years[-1]],
            "note": "Lines are fitted to eligible years only and are not drawn outside the observed period; they are not forecasts.",
        }
    else:
        out["comparison"] = None
        out["comparison_unavailable_reason"] = ols.unavailable_reason or (trend or {}).get("slope_unavailable_reason") or "Theil–Sen slope unavailable"
    return out


def _seasonal_block(trend: dict[str, Any], monthly: dict[tuple[int, int], float]) -> dict[str, Any]:
    months = list(trend.get("months_used") or [])
    years = list(trend.get("eligible_years") or [])
    used = {k: v for k, v in monthly.items() if k[1] in months and k[0] in years and _finite(v)}
    deseason = deseasonalized_ols_slope(used, months) if months else None
    return {
        "method": "seasonal_kendall",
        "months_used": months,
        "months_not_used": [m for m in range(1, 13) if m not in months],
        "month_names_used": [calendar.month_abbr[m] for m in months],
        "years_contributing": years,
        "sample_count": trend.get("sample_count", len(used)),
        "seasonal_sen_slope": trend.get("slope"),
        "slope_units": trend.get("slope_units"),
        "confidence_interval": trend.get("confidence_interval"),
        "confidence_interval_unavailable_reason": trend.get("confidence_interval_unavailable_reason"),
        "seasonal_kendall": trend.get("mann_kendall"),
        "deseasonalized_ols_slope": deseason,
        "deseasonalized_ols_unavailable_reason": None if deseason is not None else "Too few distinct monthly observations for a descriptive OLS slope",
        "comparison_note": ("Both slopes use the same monthly observations (months in at least 70% of years). The seasonal Sen "
                            "slope is a median of within-month pairwise slopes; the deseasonalized OLS slope fits monthly anomalies "
                            "by least squares. They are related but not identical estimators, and neither is an annual-value trend. "
                            "The deseasonalized OLS regresses month-centred values on decimal year without centring the time "
                            "axis within each month. On one synthetic unit-test fixture (an exactly linear series over 10 "
                            "years and 5 months) this gave a slope about 2% below the true value; that figure is specific "
                            "to that fixture, is not an expected bias for other data, and must not be used as a correction."),
        "availability_rule": "A calendar month is used only if it has data in at least 70% of the years (and at least 3 years).",
    }


def build_methods_lab(variable: str, annual: list[dict[str, Any]], trend: dict[str, Any] | None,
                      monthly: dict[tuple[int, int], float] | None = None, policy: TrendPolicy | None = None) -> dict[str, Any]:
    policy = policy or TrendPolicy()
    seasonal = bool(trend and trend.get("method") == "seasonal_kendall")
    lab: dict[str, Any] = {
        "applicable": {"annual_comparison": not seasonal, "seasonal": seasonal},
        "requirements": {
            "minimum_years_for_slope": policy.minimum_slope_years,
            "minimum_years_for_significance": policy.minimum_significance_years,
            "alpha": policy.alpha,
            "dependence_screen": f"lag-1 Spearman ρ ≥ {policy.material_lag1_rho} or p < {policy.alpha} withholds significance; at least {policy.minimum_adjacent_residual_pairs} adjacent residual pairs needed",
        },
        "mann_kendall": (trend or {}).get("mann_kendall"),
        "significance_unavailable_reason": (trend or {}).get("significance_unavailable_reason"),
        "serial_dependence": (trend or {}).get("serial_dependence"),
        "change_point": (trend or {}).get("change_point"),
        "methods": METHODS,
    }
    if seasonal:
        lab["annual_comparison_unavailable_reason"] = (
            "This variable's trend uses the Seasonal Kendall method on monthly values, so an annual OLS vs Theil–Sen "
            "comparison would use a different sample. The seasonal panel compares estimators on the same monthly observations.")
        lab["seasonal"] = _seasonal_block(trend or {}, monthly or {})
        lab["observations"] = {"basis": "monthly means in the months used by the seasonal method",
                               "eligible": [], "excluded": []}
    else:
        lab.update(_annual_block(annual, trend, policy))
        lab["seasonal"] = None
        lab["seasonal_unavailable_reason"] = "Seasonal methods apply to the NDVI analysis, which is built from monthly values."
    return lab
