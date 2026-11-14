"""Contract for the AI Earth Detective (Feature 02).

The Detective runs in the browser and answers only from the /api/v2/analysis response the user
already has. These tests pin the fields it reads, using stored real (live) Yangon responses, so a
backend change cannot silently remove evidence the assistant depends on. No new endpoint exists
for the Detective, and no field here is computed for it.
"""

import json
import math
from pathlib import Path

import pytest

from app.api.routes import unified

FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))

CASES = [("temperature", "temperature_trend"), ("relative_humidity", "rh_trend"), ("precipitation", "precip_trend"),
         ("extreme_heat", "heat_trend"), ("ndvi", "ndvi_trend")]

TREND_FIELDS = {"result_level", "result_level_label", "eligible_years", "excluded_years", "missing_years", "slope", "slope_units",
                "confidence_interval", "confidence_interval_unavailable_reason", "mann_kendall", "serial_dependence",
                "slope_unavailable_reason", "significance_unavailable_reason"}


@pytest.mark.parametrize("variable, key", CASES)
def test_analysis_response_carries_every_field_the_detective_reads(variable, key) -> None:
    out = unified.normalise(variable, FIXTURE[key], 16.8661, 96.1951)
    assert {"id", "name", "annual_value_definition"} <= set(out["variable"])
    assert {"source", "id", "version", "provenance", "doi"} <= set(out["dataset"])
    assert {"description", "resolution", "mode", "requested"} <= set(out["spatial_support"])
    assert out["period"]["start"].startswith("2015") and out["period"]["end_exclusive"].startswith("2025")
    assert {"annual_value", "slope"} <= set(out["units"])
    assert {"years_requested", "eligible_years", "excluded_years"} <= set(out["coverage"])
    assert isinstance(out["caveats"], list) and isinstance(out["limitations"], list)
    assert TREND_FIELDS <= set(out["trend"])
    for point in out["annual"]:
        assert {"year", "value", "eligible", "reasons", "represented_months"} <= set(point)


@pytest.mark.parametrize("variable, key", CASES)
def test_unavailable_values_stay_null_never_zero(variable, key) -> None:
    """The Detective treats null as unavailable; the API must not encode missing results as 0."""
    out = unified.normalise(variable, FIXTURE[key], 16.8661, 96.1951)
    trend = out["trend"]
    if trend["slope"] is None:
        assert trend["slope_unavailable_reason"]
    else:
        assert math.isfinite(trend["slope"])
    if trend["confidence_interval"] is None:
        assert trend["confidence_interval_unavailable_reason"]
    if trend["result_level"] != "statistical_inference":
        assert trend["mann_kendall"] is None or trend["significance_unavailable_reason"]
    for point in out["annual"]:
        if not point["eligible"]:
            assert point["reasons"], f"excluded year {point['year']} must carry a reason"
        if point["value"] is not None:
            assert math.isfinite(point["value"])


def test_catalog_dois_are_plain_doi_strings() -> None:
    """The Detective links only syntactically valid catalog DOIs; check the catalog provides them in that form."""
    for variable, key in CASES:
        doi = unified.normalise(variable, FIXTURE[key], 16.8661, 96.1951)["dataset"]["doi"]
        assert doi is None or (doi.startswith("10.") and "/" in doi and " " not in doi)


def test_no_detective_endpoint_is_exposed() -> None:
    from app.main import create_app

    paths = {getattr(r, "path", "") for r in create_app().routes}
    assert not any("detective" in p or "chat" in p or "assistant" in p for p in paths)
