"""Shared, conservative wording about the statistical methods (Phase 6).

The trend engine is unchanged. These notes describe its known limitations so every
endpoint communicates uncertainty the same way.
"""

INFERENCE_CAVEAT = (
    "Mann-Kendall significance is reported only after a lag-1 serial-dependence screen. "
    "An independent Monte Carlo check (5,000 replications) found that this screened test "
    "can reject a true no-trend hypothesis more often than the nominal 5% when annual "
    "values are autocorrelated (about 10.5% at n = 45, lag-1 autocorrelation 0.3). "
    "Treat 'statistically significant' as indicative, not as a guaranteed 5% "
    "false-positive rate."
)

DESCRIPTIVE_SLOPE_NOTE = (
    "The Theil-Sen slope is a robust descriptive rate of change over the eligible years "
    "only. It is not a forecast and does not identify a cause."
)

TREND_METHOD = {
    "slope": "Theil-Sen median of pairwise slopes (SciPy theilslopes, method='separate')",
    "significance": "two-sided Mann-Kendall test with tie correction, alpha from policy",
    "serial_dependence_screen": "lag-1 Spearman correlation of Theil-Sen residuals",
    "confidence_interval": "Theil-Sen 95% interval, reported only when inference is supported",
    "inference_caveat": INFERENCE_CAVEAT,
    "descriptive_slope_note": DESCRIPTIVE_SLOPE_NOTE,
}

SEASONAL_DESCRIPTIVE_SLOPE_NOTE = (
    "The seasonal Sen slope is a robust descriptive rate of change, from monthly values in the "
    "months the trend uses only. It is not a forecast and does not identify a cause."
)

SEASONAL_TREND_METHOD = {
    "slope": "seasonal Sen slope: median of within-month pairwise slopes, divided by the real year gap (Hirsch, Slack & Smith 1982)",
    "significance": "two-sided Seasonal Kendall test: Mann-Kendall S and tie-corrected variance summed over calendar months",
    "months": "a calendar month is used only if it has values in at least 70% of the requested years",
    "why": "cloud-masked months (for example the monsoon) rarely leave complete years for the annual method; "
           "comparing each month only with the same month in other years needs no complete years",
    "confidence_interval": "rank-based 95% interval for the seasonal Sen slope, reported only when inference is supported",
    "not_applied": "Hirsch-Slack correction for correlation between adjacent months; the p-value may be optimistic",
    "descriptive_slope_note": SEASONAL_DESCRIPTIVE_SLOPE_NOTE,
}
