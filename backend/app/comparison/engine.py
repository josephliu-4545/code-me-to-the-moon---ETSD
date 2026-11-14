"""Descriptive comparison of independently analysed datasets.

Each dataset keeps its own result. Numbers are compared directly only when the
catalog marks the datasets as measuring the same quantity in the same units.
Nothing here merges, averages or gap-fills datasets, treats one dataset as truth,
or computes significance for differences.
"""

from itertools import combinations
from statistics import mean
from typing import Any

from scipy.stats import pearsonr, spearmanr, theilslopes

from app.comparison.catalog import DatasetEntry, relationship


MIN_COMMON_YEARS_FOR_CORRELATION = 8
MIN_COMMON_YEARS_FOR_SLOPE = 3


def _eligible_values(analysis: dict[str, Any]) -> dict[int, float]:
    return {a["year"]: float(a["value"]) for a in analysis["annual"] if a["eligible"] and a["value"] is not None}


def _finite(x: float) -> float | None:
    return None if x != x else float(x)


def _rho(x: list[float], y: list[float]) -> float | None:
    """Spearman rho, or None when either series is constant (correlation undefined)."""
    if len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return _finite(spearmanr(x, y).statistic)


def compare_pair(a: DatasetEntry, b: DatasetEntry, ra: dict[str, Any], rb: dict[str, Any]) -> dict[str, Any]:
    lineage, lineage_note = relationship(a, b)
    out: dict[str, Any] = {"datasets": [a.key, b.key], "lineage": lineage, "lineage_note": lineage_note,
                           "unavailable_reasons": []}
    comparable = a.comparable_quantity == b.comparable_quantity and ra["units"]["annual_value"] == rb["units"]["annual_value"]
    out["numerically_comparable"] = comparable
    if not comparable:
        out["not_comparable_reason"] = (
            f"{a.name} measures '{a.comparable_quantity}' ({ra['units']['annual_value']}) and {b.name} measures "
            f"'{b.comparable_quantity}' ({rb['units']['annual_value']}); annual values are shown separately and not differenced.")
    va, vb = _eligible_values(ra), _eligible_values(rb)
    common = sorted(set(va) & set(vb))
    out["common_eligible_years"] = common
    ta, tb = ra.get("trend") or {}, rb.get("trend") or {}
    sa, sb = ta.get("slope"), tb.get("slope")
    out["full_period_slopes"] = {a.key: sa, b.key: sb}
    out["slope_sign_agreement"] = None if sa is None or sb is None else ((sa > 0) - (sa < 0)) == ((sb > 0) - (sb < 0))
    cia, cib = ta.get("confidence_interval"), tb.get("confidence_interval")
    out["confidence_intervals_overlap"] = None if not (cia and cib and comparable) else bool(cia[0] <= cib[1] and cib[0] <= cia[1])

    if len(common) >= MIN_COMMON_YEARS_FOR_SLOPE:
        xa = [va[y] for y in common]
        xb = [vb[y] for y in common]
        out["common_period_slopes"] = {
            a.key: float(theilslopes(xa, x=common, method="separate").slope),
            b.key: float(theilslopes(xb, x=common, method="separate").slope),
        }
    else:
        out["common_period_slopes"] = None
        out["unavailable_reasons"].append("fewer_than_3_common_eligible_years")

    if comparable and common:
        diffs = [va[y] - vb[y] for y in common]
        out["annual_differences"] = [{"year": y, "difference": d} for y, d in zip(common, diffs)]
        out["mean_difference"] = mean(diffs)
        out["mean_absolute_difference"] = mean(abs(d) for d in diffs)
        out["difference_units"] = ra["units"]["annual_value"]
        out["difference_label"] = "first minus second; a systematic difference, not an error — neither dataset is ground truth"
    else:
        out["annual_differences"] = None
        out["mean_difference"] = out["mean_absolute_difference"] = None

    if len(common) >= MIN_COMMON_YEARS_FOR_CORRELATION:
        xa = [va[y] for y in common]
        xb = [vb[y] for y in common]
        out["spearman_rho"] = _rho(xa, xb)
        out["pearson_r"] = _finite(pearsonr(xa, xb).statistic) if len(set(xa)) > 1 and len(set(xb)) > 1 else None
        consecutive = [(i, i + 1) for i in range(len(common) - 1) if common[i + 1] - common[i] == 1]
        if len(consecutive) >= MIN_COMMON_YEARS_FOR_CORRELATION - 1:
            da = [xa[j] - xa[i] for i, j in consecutive]
            db = [xb[j] - xb[i] for i, j in consecutive]
            out["spearman_rho_year_to_year"] = _rho(da, db)
        else:
            out["spearman_rho_year_to_year"] = None
    else:
        out["spearman_rho"] = out["pearson_r"] = out["spearman_rho_year_to_year"] = None
        out["unavailable_reasons"].append("fewer_than_8_common_eligible_years_for_correlation")
    return out


def agreement_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    signs = [p["slope_sign_agreement"] for p in pairs if p["slope_sign_agreement"] is not None]
    rhos = [p["spearman_rho"] for p in pairs if p["spearman_rho"] is not None]
    if not pairs:
        level = "not_assessable"
    elif signs and all(signs) and rhos and min(rhos) >= 0.7:
        level = "consistent"
    elif signs and not any(signs):
        level = "conflicting_trend_direction"
    elif signs and not all(signs):
        level = "mixed"
    elif rhos:
        level = "partially_assessable"
    else:
        level = "not_assessable"
    return {
        "level": level,
        "slope_sign_agreement_all": (all(signs) if signs else None),
        "min_spearman_rho": min(rhos) if rhos else None,
        "explanation": {
            "consistent": "Trend directions agree and year-to-year values co-vary strongly (ρ ≥ 0.7) over common years.",
            "mixed": "Some dataset pairs agree on trend direction and others do not.",
            "conflicting_trend_direction": "The datasets disagree on the direction of the trend.",
            "partially_assessable": "Values co-vary but trend directions cannot all be compared.",
            "not_assessable": "Too few successful datasets or common eligible years to assess agreement.",
        }[level],
        "caution": "Agreement between datasets does not prove accuracy, especially when they share inputs; disagreement does not show which dataset is wrong.",
    }


def compare(results: list[tuple[DatasetEntry, dict[str, Any]]]) -> dict[str, Any]:
    pairs = [compare_pair(a, b, ra, rb) for (a, ra), (b, rb) in combinations(results, 2)]
    quantities = {e.comparable_quantity for e, _ in results}
    years = [set(_eligible_values(r)) for _, r in results]
    return {
        "pairs": pairs,
        "all_numerically_comparable": len(quantities) == 1 and len({r["units"]["annual_value"] for _, r in results}) == 1,
        "common_eligible_years_all": sorted(set.intersection(*years)) if years else [],
        "agreement": agreement_summary(pairs),
        "method": {
            "pairing": "only calendar years eligible in both datasets are paired",
            "common_period_slope": "Theil–Sen slope of each dataset over the common eligible years only (descriptive, no inference)",
            "correlation": f"Spearman ρ and Pearson r of annual values, and Spearman ρ of year-to-year changes; withheld below {MIN_COMMON_YEARS_FOR_CORRELATION} common years; no p-values",
            "differences": "computed only for datasets measuring the same quantity in the same units",
        },
    }
