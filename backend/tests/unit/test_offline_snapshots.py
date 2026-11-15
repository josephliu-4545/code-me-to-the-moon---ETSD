"""Offline demo snapshots must match the current /api/v2/analysis contract.

The frontend shows these saved live retrievals only when the backend is unreachable. Every page reads
the same files, so an outdated schema (for example a snapshot from before the Seasonal Kendall NDVI
trend or the Statistical Methods Lab) would make pages contradict each other or the live app. These
tests read the committed files only; no network.
"""

from datetime import datetime
import json
import math
from pathlib import Path

import pytest

from app.api.routes import unified

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS = ROOT / "frontend" / "public" / "snapshots"
FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))
INDEX = json.loads((SNAPSHOTS / "index.json").read_text(encoding="utf-8"))
ENTRIES = INDEX["entries"]
EXPECTED = {
    ("temperature", None), ("relative_humidity", None), ("extreme_heat", None), ("precipitation", None),
    ("ndvi", None), ("soil_moisture", "gldas_2_1_noah_0_10cm"), ("soil_moisture", "smap_l3e_v006_am"),
}
LEVELS = {"statistical_inference", "descriptive_slope", "annual_summaries_only"}


def load(entry: dict) -> dict:
    return json.loads((SNAPSHOTS / entry["file"]).read_text(encoding="utf-8"))


def current_top_level_fields() -> set[str]:
    """Fields the current API returns (from the unified adapter on a stored live response), minus the per-process cache."""
    return set(unified.normalise("temperature", FIXTURE["temperature_trend"], 16.8661, 96.1951)) - {"cache"}


def test_index_records_capture_provenance_and_the_demo_request() -> None:
    datetime.fromisoformat(INDEX["captured_at"])
    assert INDEX["generator"] == "backend/scripts/capture_snapshots.py"
    assert "not a fresh query" in INDEX["note"]
    assert INDEX["request"] == {"latitude": 16.8661, "longitude": 96.1951, "start_date": "2015-01-01", "end_date_exclusive": "2025-01-01"}
    assert {(e["variable"], e.get("dataset")) for e in ENTRIES} == EXPECTED
    for e in ENTRIES:
        datetime.fromisoformat(e["retrieved_at"])
        assert e["original_data_status"] in {"live_nasa_retrieval", "cached_nasa_retrieval"}
        assert (e["latitude"], e["longitude"], e["startYear"], e["endYear"], e["mode"]) == (16.8661, 96.1951, 2015, 2025, "point")
        assert (SNAPSHOTS / e["file"]).is_file()


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["file"])
def test_snapshot_has_every_field_of_the_current_api(entry) -> None:
    body = load(entry)
    missing = current_top_level_fields() - set(body)
    assert not missing, f"{entry['file']} is missing current API fields {sorted(missing)}: regenerate the snapshots"
    assert "cache" not in body and body["data_status"] == "saved_snapshot"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["file"])
def test_identity_provenance_and_spatial_support_match_the_request(entry) -> None:
    body = load(entry)
    assert body["variable"]["id"] == entry["variable"]
    assert body["dataset"]["id"] == entry["dataset_id"] and body["dataset"]["version"] == entry["dataset_version"]
    assert body["dataset"]["provenance"]
    if entry.get("dataset"):
        assert body["dataset"]["key"] == entry["dataset"]
    assert (body["period"]["start"], body["period"]["end_exclusive"]) == ("2015-01-01", "2025-01-01")
    support = body["spatial_support"]
    assert support["mode"] == "point" and support["requested"] == {"latitude": 16.8661, "longitude": 96.1951}
    assert support["description"] and support["resolution"]


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["file"])
def test_annual_observations_and_missing_data_are_never_zero_filled(entry) -> None:
    body = load(entry)
    years = [a["year"] for a in body["annual"]]
    assert years == list(range(2015, 2025))
    assert body["coverage"]["years_requested"] == 10
    for a in body["annual"]:
        assert a["value"] is None or math.isfinite(a["value"])
        if not a["eligible"]:
            assert a["reasons"], f"{entry['file']} {a['year']}: excluded year without a reason"
    assert body["coverage"]["eligible_years"] == sum(a["eligible"] for a in body["annual"])


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["file"])
def test_trend_fields_are_internally_consistent(entry) -> None:
    t = load(entry)["trend"]
    assert t["result_level"] in LEVELS
    if t["slope"] is None:
        assert t["slope_unavailable_reason"] and t["result_level"] == "annual_summaries_only"
    else:
        assert math.isfinite(t["slope"]) and t["slope_units"]
    if t["confidence_interval"] is None:
        assert t["confidence_interval_unavailable_reason"] or t["slope_unavailable_reason"]
    else:
        lo, hi = t["confidence_interval"]
        assert math.isfinite(lo) and math.isfinite(hi) and lo <= hi
    if t["result_level"] == "statistical_inference":
        assert t["mann_kendall"] is not None and 0 <= t["mann_kendall"]["p_value"] <= 1
    else:
        assert t["significance_unavailable_reason"]


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["file"])
def test_methods_lab_evidence_matches_the_trend_method(entry) -> None:
    body = load(entry)
    lab, t = body["methods_lab"], body["trend"]
    seasonal = t.get("method") == "seasonal_kendall"
    assert lab["applicable"]["seasonal"] is seasonal
    if seasonal:
        assert lab["seasonal"]["months_used"] == t["months_used"]
        assert lab["seasonal"]["seasonal_sen_slope"] == t["slope"]
    elif t["slope"] is not None:
        assert lab["theil_sen"]["slope"] == t["slope"]
        assert lab["ols"]["inference"] is None  # OLS stays descriptive
    else:
        assert lab["ols"]["slope"] is None and (lab.get("comparison_unavailable_reason") or lab["ols"]["unavailable_reason"])


def by_file(fragment: str) -> dict:
    return load(next(e for e in ENTRIES if fragment in e["file"]))


def test_ndvi_snapshot_uses_the_current_seasonal_method() -> None:
    t = by_file("ndvi")["trend"]
    assert t["method"] == "seasonal_kendall" and t["months_used"] and t["sample_count"] > 0
    assert t["slope"] is not None and t["slope_units"].endswith("/year")


def test_smap_keeps_its_genuine_unavailable_outcome_and_quality_control_record() -> None:
    body = by_file("smap_l3e_v006_am")
    assert body["trend"]["slope"] is None and body["coverage"]["eligible_years"] == 0
    diagnostics = body["extra"]["diagnostics"]
    assert diagnostics["valid_retrievals"] == 0 and diagnostics["qc_rejected_retrievals"] > 0
    assert body["dataset"]["depth"]["semantics"] == "approximate_sensing_depth"


def test_gldas_snapshot_records_its_model_layer() -> None:
    body = by_file("gldas_2_1_noah_0_10cm")
    assert body["dataset"]["depth"] == {"top_cm": 0.0, "bottom_cm": 10.0, "semantics": "model_layer"}
    assert "diagnostics" in body["extra"]


def test_no_configuration_or_credentials_are_published() -> None:
    text = "".join(p.read_text(encoding="utf-8") for p in SNAPSHOTS.glob("*.json"))
    for forbidden in ("PRIVATE KEY", "private_key", "client_email", "gserviceaccount", "EE_PROJECT_ID", "X-API-Key"):
        assert forbidden not in text


def test_variables_catalog_snapshot_matches_the_live_catalog_shape() -> None:
    saved = json.loads((SNAPSHOTS / "variables.json").read_text(encoding="utf-8"))
    assert {v["id"] for v in saved["variables"]} == {"temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"}
    assert saved["api_version"] and saved["caveats"]
