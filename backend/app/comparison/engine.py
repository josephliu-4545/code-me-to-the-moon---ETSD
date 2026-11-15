"""Descriptive comparison of independently analysed datasets.

Each dataset keeps its own result. Numbers are compared directly only when the
catalog marks the datasets as measuring the same quantity in the same units.
Nothing here merges, averages or gap-fills datasets, treats one dataset as truth,
or computes significance for differences.
"""

from itertools import combinations
from math import sqrt
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


def _metric(metric_id: str, name: str, value: Any, units: str | None, count: int,
            definition: str, interpretation: str, limitations: str,
            unavailable_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": name,
        "value": value,
        "units": units,
        "matched_observations": count,
        "definition": definition,
        "interpretation": interpretation,
        "limitations": limitations,
        "availability": "available" if value is not None else "unavailable",
        "unavailable_reason": unavailable_reason,
    }


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
    labels_a, labels_b = [str(y) for y in sorted(va)], [str(y) for y in sorted(vb)]
    out["matched_observations"] = {
        "resolution": "annual",
        "count": len(common),
        "period": ({"start": str(common[0]), "end": str(common[-1])} if common else None),
        "labels": [str(y) for y in common],
        "valid_observations": {a.key: labels_a, b.key: labels_b},
        "excluded_from_pairing": {
            a.key: [str(y) for y in sorted(set(va) - set(common))],
            b.key: [str(y) for y in sorted(set(vb) - set(common))],
        },
        "quality_excluded": {
            a.key: [str(row["year"]) for row in ra.get("annual", []) if not row.get("eligible")],
            b.key: [str(row["year"]) for row in rb.get("annual", []) if not row.get("eligible")],
        },
    }
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
        out["slope_difference"] = (
            out["common_period_slopes"][a.key] - out["common_period_slopes"][b.key]
            if comparable else None
        )
        common_sa = out["common_period_slopes"][a.key]
        common_sb = out["common_period_slopes"][b.key]
        out["common_period_slope_sign_agreement"] = (
            (common_sa > 0) - (common_sa < 0) == (common_sb > 0) - (common_sb < 0)
        )
    else:
        out["common_period_slopes"] = None
        out["slope_difference"] = None
        out["common_period_slope_sign_agreement"] = None
        out["unavailable_reasons"].append("fewer_than_3_common_eligible_years")
    out["direction_evidence"] = _direction_evidence(out, ta, tb, va, vb, common)

    if comparable and common:
        diffs = [va[y] - vb[y] for y in common]
        out["annual_differences"] = [{"year": y, "difference": d} for y, d in zip(common, diffs)]
        out["mean_difference"] = mean(diffs)
        out["mean_absolute_difference"] = mean(abs(d) for d in diffs)
        out["root_mean_square_difference"] = sqrt(mean(d * d for d in diffs))
        out["difference_units"] = ra["units"]["annual_value"]
        out["difference_label"] = "first minus second; a systematic difference, not an error — neither dataset is ground truth"
    else:
        out["annual_differences"] = None
        out["mean_difference"] = out["mean_absolute_difference"] = None
        out["root_mean_square_difference"] = None

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
    direct_unavailable = (
        "Datasets measure different physical quantities or use incompatible units."
        if not comparable else ("No common eligible years." if not common else None)
    )
    slope_unavailable = direct_unavailable or (
        None if out["slope_difference"] is not None else "Fewer than 3 common eligible years for common-period slopes."
    )
    if not common:
        correlation_unavailable = "No common eligible years."
    elif len(common) < MIN_COMMON_YEARS_FOR_CORRELATION:
        correlation_unavailable = f"Requires at least {MIN_COMMON_YEARS_FOR_CORRELATION} common eligible years."
    elif len({va[y] for y in common}) < 2 or len({vb[y] for y in common}) < 2:
        correlation_unavailable = "Correlation is undefined because one or both matched series are constant."
    else:
        correlation_unavailable = None
    direction_unavailable = (
        None if out["common_period_slope_sign_agreement"] is not None
        else ("No common eligible years." if not common else "Fewer than 3 common eligible years for common-period slopes.")
    )
    product_difference = "A product-to-product difference; it is not an error or established bias."
    no_truth = "Neither product is treated as ground truth; spatial footprints and production methods differ."
    out["metrics"] = [
        _metric("mean_difference", "Signed mean difference", out["mean_difference"], out.get("difference_units"), len(common),
                "Mean of Dataset A minus Dataset B over matched eligible years.", product_difference, no_truth, direct_unavailable),
        _metric("mae", "Mean absolute difference", out["mean_absolute_difference"], out.get("difference_units"), len(common),
                "Mean absolute Dataset A minus Dataset B difference over matched eligible years.", product_difference, no_truth, direct_unavailable),
        _metric("rmse", "Root mean square difference", out["root_mean_square_difference"], out.get("difference_units"), len(common),
                "Square root of the mean squared Dataset A minus Dataset B differences over matched eligible years.", product_difference, no_truth, direct_unavailable),
        _metric("pearson_r", "Pearson correlation", out["pearson_r"], None, len(common),
                "Linear correlation of matched annual values.", "Describes co-variation, not accuracy or causation.",
                "Sensitive to outliers and serial structure; no p-value is reported.", correlation_unavailable),
        _metric("spearman_rho", "Spearman rank correlation", out["spearman_rho"], None, len(common),
                "Rank correlation of matched annual values.", "Describes monotonic co-variation, not accuracy or causation.",
                "No p-value is reported; shared inputs can inflate agreement.", correlation_unavailable),
        _metric("trend_direction", "Common-period trend-direction agreement",
                out["common_period_slope_sign_agreement"], None, len(common),
                "Whether the signs of the two Theil–Sen slopes over the common eligible years are equal.",
                "Shows directional consistency over matched years only.",
                "Descriptive only; the legacy Comparison view retains each dataset's full-request trend.",
                direction_unavailable),
        _metric("slope_difference", "Difference in common-period slopes", out["slope_difference"],
                ta.get("slope_units") or rb.get("units", {}).get("slope"), len(common),
                "Dataset A common-period Theil–Sen slope minus Dataset B common-period Theil–Sen slope.", product_difference,
                "Descriptive only; trends are not treated as independent observations.", slope_unavailable),
    ]
    return out


DIRECTION_SIGN = {
    "descriptive_same_direction": True,
    "indicative_same_direction": True,
    "descriptive_opposite_direction": False,
    "indicative_opposite_direction": False,
}

LEVEL_LABELS = {
    "consistent": "Same {kind} direction, strong co-variation",
    "same_direction_weak_covariation": "Same {kind} direction, weak co-variation",
    "same_direction_covariation_not_assessable": "Same {kind} direction; co-variation not assessable",
    "conflicting_trend_direction": "Opposite {kind} slope directions",
    "mixed": "Mixed {kind} directions",
    "partially_assessable": "Partially assessable: {assessed} of {total} pairs compared",
    "not_assessable": "Not assessable",
}

LEVEL_EXPLANATIONS = {
    "consistent": "Over common eligible years, every pair's slopes point the same way and every pair's annual values co-vary strongly (Spearman ρ ≥ 0.7).",
    "same_direction_weak_covariation": "Over common eligible years, every pair's slopes point the same way, but at least one pair's annual values co-vary only weakly (Spearman ρ < 0.7).",
    "same_direction_covariation_not_assessable": "Over common eligible years, every pair's slopes point the same way. Co-variation is not assessed for every pair: correlation needs at least 8 common eligible years.",
    "conflicting_trend_direction": "Over common eligible years, the slopes of every pair point in opposite directions.",
    "mixed": "Over common eligible years, some pairs' slopes point the same way and others in opposite directions.",
    "partially_assessable": "Slope directions over common eligible years could be compared for only some dataset pairs. No overall conclusion is drawn; the available pairwise findings are listed.",
    "not_assessable": "Too few successful datasets or common eligible years to compare slope directions or co-variation.",
}

DESCRIPTIVE_NOTE = (
    " These are descriptive Theil–Sen slopes over the matched years with no significance test on that sample, "
    "so this is not an established agreement or conflict; slopes near zero can point either way by chance."
)
INDICATIVE_NOTE = (
    " Each dataset's own significance test covers exactly these common years and indicates a monotonic trend "
    "(indicative only; autocorrelation can inflate false positives)."
)


def _direction_evidence(out: dict[str, Any], ta: dict[str, Any], tb: dict[str, Any],
                        va: dict[int, float], vb: dict[int, float], common: list[int]) -> str:
    """How the pair's slope directions over common eligible years may be read.

    "indicative_*" only when both datasets' own Mann-Kendall tests were run on exactly the common
    years (their eligible years equal the overlap) and both are significant; full-period results
    otherwise describe a different sample and are not transferred. Everything else is descriptive.
    No new test or interval is computed here.
    """
    agree = out["common_period_slope_sign_agreement"]
    slopes = out["common_period_slopes"]
    if agree is None or not slopes:
        return "unavailable"
    if any(v == 0 for v in slopes.values()):
        return "descriptive_no_direction"

    def tested_on_common_years(trend: dict[str, Any], values: dict[int, float]) -> bool:
        mk = trend.get("mann_kendall") or {}
        return (trend.get("result_level") == "statistical_inference"
                and mk.get("is_statistically_significant") is True and set(values) == set(common))

    kind = "indicative" if tested_on_common_years(ta, va) and tested_on_common_years(tb, vb) else "descriptive"
    return f"{kind}_{'same' if agree else 'opposite'}_direction"


def _pair_name(p: dict[str, Any], names: dict[str, str] | None) -> str:
    keys = p.get("datasets") or ["?", "?"]
    return " vs ".join((names or {}).get(k, k) for k in keys)


def _direction_word(evidence: str) -> str:
    return {
        "descriptive_same_direction": "same direction (descriptive)",
        "indicative_same_direction": "same direction (indicative)",
        "descriptive_opposite_direction": "opposite directions (descriptive)",
        "indicative_opposite_direction": "opposite directions (indicative)",
        "descriptive_no_direction": "no direction (a slope is exactly zero)",
    }.get(evidence, "not assessable (fewer than 3 common eligible years)")


def agreement_summary(pairs: list[dict[str, Any]], names: dict[str, str] | None = None) -> dict[str, Any]:
    """Headline agreement from matched (common-period) evidence only.

    The headline describes all pairs only when every pair was assessed. If only some pairs have a
    common-period direction, the level is `partially_assessable` and no overall direction is claimed;
    the available pairwise findings are kept in `pair_findings`. Co-variation (strong/weak) is
    summarised only when every pair has a correlation, and the weakest pair is named. Level
    identifiers are kept for API compatibility; their meaning is descriptive. Full-request slope
    signs are never used here.
    """
    def evidence(p: dict[str, Any]) -> str:
        if "direction_evidence" in p:
            return p["direction_evidence"]
        legacy = p.get("common_period_slope_sign_agreement")  # summaries built from minimal dicts
        return "unavailable" if legacy is None else ("descriptive_same_direction" if legacy else "descriptive_opposite_direction")

    kinds = [evidence(p) for p in pairs]
    total = len(pairs)
    assessed_idx = [i for i, k in enumerate(kinds) if k in DIRECTION_SIGN]
    assessed = [kinds[i] for i in assessed_idx]
    signs = [DIRECTION_SIGN[k] for k in assessed]
    rho_pairs = [(p, p["spearman_rho"]) for p in pairs if p.get("spearman_rho") is not None]
    rhos = [r for _, r in rho_pairs]

    direction_coverage = "none" if not assessed else ("complete" if len(assessed) == total else "partial")
    covariation_coverage = "none" if not rho_pairs else ("complete" if len(rho_pairs) == total else "partial")

    if not pairs or direction_coverage == "none":
        level = "not_assessable"
    elif direction_coverage == "partial":
        level = "partially_assessable"
    elif all(signs):
        if covariation_coverage == "complete":
            level = "consistent" if min(rhos) >= 0.7 else "same_direction_weak_covariation"
        else:
            level = "same_direction_covariation_not_assessable"
    elif not any(signs):
        level = "conflicting_trend_direction"
    else:
        level = "mixed"

    if assessed and all(k.startswith("indicative") for k in assessed):
        direction_kind = "indicative"
    else:
        direction_kind = "descriptive" if assessed else "unavailable"

    explanation = LEVEL_EXPLANATIONS[level]
    if level == "partially_assessable":
        listed = "; ".join(f"{_pair_name(p, names)}: {_direction_word(k)}" for p, k in zip(pairs, kinds))
        explanation += f" Directions were compared for {len(assessed)} of {total} pairs ({listed})."
    if assessed:
        explanation += INDICATIVE_NOTE if direction_kind == "indicative" else DESCRIPTIVE_NOTE
    if rho_pairs:
        weakest_pair, weakest = min(rho_pairs, key=lambda item: item[1])
        if covariation_coverage == "complete":
            explanation += (f" Spearman ρ is available for all {total} pair(s); the lowest is "
                            f"{weakest:.2f} ({_pair_name(weakest_pair, names)}).")
        else:
            listed_rho = "; ".join(f"{_pair_name(p, names)} ρ = {r:.2f}" for p, r in rho_pairs)
            explanation += (f" Spearman ρ is available for only {len(rho_pairs)} of {total} pairs ({listed_rho}), "
                            "so co-variation is not summarised across all pairs.")

    not_comparable = any(p.get("numerically_comparable") is False for p in pairs)
    shared = any(p.get("lineage") in {"same_lineage", "partially_related"} for p in pairs)
    label_kind = "indicative" if direction_kind == "indicative" else "descriptive"
    return {
        "level": level,
        "label": LEVEL_LABELS[level].format(kind=label_kind, assessed=len(assessed), total=total),
        "basis": "common_period_descriptive_slopes",
        "direction_evidence": direction_kind,
        "direction_coverage": direction_coverage,
        "covariation_coverage": covariation_coverage,
        "pairs_total": total,
        "pairs_with_direction": len(assessed),
        "pairs_without_direction": total - len(assessed),
        "pairs_with_correlation": len(rho_pairs),
        "pair_findings": [
            {"datasets": list(p.get("datasets") or []), "direction_evidence": k,
             "spearman_rho": p.get("spearman_rho"), "common_eligible_years": len(p.get("common_eligible_years") or [])}
            for p, k in zip(pairs, kinds)
        ],
        # True/False only when every pair was assessed (never an "all pairs" claim from a subset).
        "slope_sign_agreement_all": (all(signs) if direction_coverage == "complete" else None),
        # Lowest rho among the pairs that have one; see pairs_with_correlation and covariation_coverage.
        "min_spearman_rho": min(rhos) if rhos else None,
        "explanation": explanation,
        "comparability_note": (
            "Some datasets measure different quantities or units: they are compared by slope direction only, not by magnitude."
            if not_comparable else None),
        "independence_note": (
            "Some datasets share inputs or lineage (not independent), so their agreement is not an independent confirmation."
            if shared else None),
        "caution": ("Agreement between datasets does not prove accuracy, especially when they share inputs; disagreement "
                    "does not show which dataset is wrong. Correlation describes association, can be inflated by shared "
                    "long-term trends, and is not evidence of causation."),
    }


def compare(results: list[tuple[DatasetEntry, dict[str, Any]]]) -> dict[str, Any]:
    pairs = [compare_pair(a, b, ra, rb) for (a, ra), (b, rb) in combinations(results, 2)]
    quantities = {e.comparable_quantity for e, _ in results}
    years = [set(_eligible_values(r)) for _, r in results]
    return {
        "pairs": pairs,
        "all_numerically_comparable": len(quantities) == 1 and len({r["units"]["annual_value"] for _, r in results}) == 1,
        "common_eligible_years_all": sorted(set.intersection(*years)) if years else [],
        "agreement": agreement_summary(pairs, {e.key: e.name for e, _ in results}),
        "method": {
            "pairing": "only calendar years eligible in both datasets are paired",
            "common_period_slope": "Theil–Sen slope of each dataset over the common eligible years only (descriptive, no inference)",
            "direction_metric": "headline agreement and the Evaluation Lab both use common-period slopes (descriptive unless each dataset's own test covers exactly the common years); the per-pair full-request sign (slope_sign_agreement) is kept only for backward compatibility",
            "correlation": f"Spearman ρ and Pearson r of annual values, and Spearman ρ of year-to-year changes; withheld below {MIN_COMMON_YEARS_FOR_CORRELATION} common years; no p-values",
            "differences": "computed only for datasets measuring the same quantity in the same units",
        },
    }
