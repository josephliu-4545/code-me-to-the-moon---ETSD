from datetime import date, timedelta
import math

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.earth_engine import EarthEngineInitializationError
from app.main import create_app
from app.services.soil_moisture_provider import EarthEngineSoilMoistureProvider
from app.services.soil_moisture_service import SoilMoistureService


class FakeManager:
    ee = None

    def initialize(self) -> None:
        pass


SPREAD = [2, 5, 8, 12, 15, 18, 22, 25, 28]
AVAIL = {
    "NASA/GLDAS/V021/NOAH/G025/T3H": ["2000-01-01", "2026-10-15"],
    "NASA/SMAP/SPL3SMP_E/005": ["2015-03-31", "2023-12-02"],
    "NASA/SMAP/SPL3SMP_E/006": ["2015-03-31", "2026-11-10"],
}


def months(start, end):
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def gldas_loader(tsoil=290.0):
    def load(d, cell, s, e):
        rows = []
        for m in months(s, e):
            n = 248 - (8 if m.month in (4, 6, 9, 11) else 0) - (24 if m.month == 2 else 0)
            if m.month == 2 and m.year % 4 == 0:
                n += 8
            value = 24.0 + 0.3 * (m.year - 2015) + 2 * math.sin(m.month) + 0.05 * ((m.year * 7) % 5)
            rows.append([m.isoformat(), n, n, n, n, n, value, tsoil if m.month != 1 else min(tsoil, 290.0)])
        return rows
    return load


def smap_loader(flag=0):
    def load(d, cell, s, e):
        first, last = (date.fromisoformat(x) for x in AVAIL[d.collection_ids[0]])
        images, rows, day = [], [], max(s, first)
        while day < e and day <= last:
            images.append(day.isoformat())
            if day.day in SPREAD:
                value = 0.21 + 0.03 * math.sin(day.month) + 0.002 * (day.year - 2015)
                rows.append([day.isoformat(), value, flag])
            day += timedelta(days=1)
        return {"images": images, "rows": rows}
    return load


def make_client(gldas=None, smap=None, neighbours=9, settings_kw=None):
    provider = EarthEngineSoilMoistureProvider(
        FakeManager(),
        gldas_loader=gldas or gldas_loader(),
        smap_loader=smap or smap_loader(),
        availability_loader=lambda d: AVAIL[d.collection_ids[0]],
        neighbourhood_loader=lambda d, c, m: neighbours,
    )
    app = create_app(Settings(_env_file=None, ee_project_id="test", **(settings_kw or {})),
                     soil_moisture_service=SoilMoistureService(provider))
    return TestClient(app)


Q = {"latitude": 38.5, "longitude": -98.5, "start_date": "2015-01-01", "end_date": "2025-01-01"}


def test_datasets_endpoint_lists_three_separate_datasets() -> None:
    body = make_client().get("/api/v1/soil-moisture/datasets").json()
    keys = [d["key"] for d in body["datasets"]]
    assert keys == ["gldas_2_1_noah_0_10cm", "smap_l3e_v005_am", "smap_l3e_v006_am"]
    assert body["datasets_are_merged"] is False
    gldas = body["datasets"][0]
    assert gldas["provenance"] == "model" and gldas["native_units"] == "kg m-2"
    assert gldas["depth"] == {"top_cm": 0.0, "bottom_cm": 10.0, "semantics": "model_layer"}


def test_gldas_trend_response_carries_provenance_units_and_trends() -> None:
    r = make_client().get("/api/v1/soil-moisture/trend", params={**Q, "dataset": "gldas_2_1_noah_0_10cm"})
    assert r.status_code == 200
    body = r.json()
    assert body["dataset"]["collection_id"] == "NASA/GLDAS/V021/NOAH/G025/T3H"
    assert body["location"]["support_type"] == "native_grid_cell"
    assert body["location"]["substituted_cell"] is False
    assert body["location"]["cell_status"] == "ok"
    assert body["units"] == {"primary": "kg m-2", "derived": "m3 m-3",
                             "derivation": "theta = S / (1000 kg m-3 x 0.10 m)",
                             "derived_is_layer_mean_not_equivalent_to_smap": True}
    assert len(body["monthly"]) == 120
    assert body["trend"]["result_level"] in {"statistical_inference", "descriptive_slope"}
    assert body["trend"]["theil_sen"]["slope_units"] == "kg m-2/year"
    assert body["derived_trend"]["theil_sen"]["slope_units"] == "m3 m-3/year"
    assert body["derived_trend"]["theil_sen"]["slope"] == pytest.approx(body["trend"]["theil_sen"]["slope"] / 100)
    assert body["methodology"]["thresholds_are_universal_standards"] is False
    assert "inference_caveat" in body["methodology"]["trend_method"]


def test_series_endpoint_omits_trend() -> None:
    body = make_client().get("/api/v1/soil-moisture", params={**Q, "dataset": "gldas_2_1_noah_0_10cm"}).json()
    assert "trend" not in body and len(body["annual_summaries"]) == 10


def test_smap_cell_failing_quality_control_reports_unavailable_honestly() -> None:
    client = make_client(smap=smap_loader(flag=1))
    body = client.get("/api/v1/soil-moisture/trend", params={
        **Q, "latitude": 16.8661, "longitude": 96.1951, "dataset": "smap_l3e_v006_am",
        "start_date": "2016-01-01"}).json()
    assert body["location"]["cell_status"] == "no_valid_land_values"
    assert body["limitations"][0].startswith("The grid cell containing this point has no valid values")
    assert body["trend"]["result_level"] == "annual_summaries_only"
    assert all(m["mean_native"] is None and m["descriptive_mean_native"] is None for m in body["monthly"])
    assert body["diagnostics"]["qc_rejected_retrievals"] > 0


def test_v005_months_after_its_record_are_outside_availability() -> None:
    body = make_client().get("/api/v1/soil-moisture", params={
        **Q, "dataset": "smap_l3e_v005_am", "start_date": "2023-01-01", "end_date": "2024-07-01"}).json()
    status = {m["month"]: m["status"] for m in body["monthly"]}
    assert status["2024-01-01"] == "outside_availability"
    assert status["2023-06-01"] == "valid"


def test_coastal_proximity_is_flagged_without_substitution() -> None:
    body = make_client(neighbours=5).get("/api/v1/soil-moisture", params={
        **Q, "dataset": "gldas_2_1_noah_0_10cm"}).json()
    assert body["location"]["coastal_proximity"] is True
    assert body["location"]["valid_cells_in_3x3"] == 5
    assert any("5 of the 9 surrounding" in t for t in body["limitations"])


def test_gldas_forcing_change_caveats_are_added_when_spanned() -> None:
    body = make_client().get("/api/v1/soil-moisture", params={
        **Q, "dataset": "gldas_2_1_noah_0_10cm", "start_date": "2010-01-01", "end_date": "2026-01-01"}).json()
    text = " ".join(body["limitations"])
    assert "post-2011 AGRMET" in text and "GALWEM" in text


@pytest.mark.parametrize(
    "params, fragment",
    [
        ({"dataset": "smap_l3e_am"}, "unknown soil moisture dataset"),
        ({"dataset": "gldas_2_1_noah_0_10cm", "radius_km": 5}, "radius_km"),
        ({"dataset": "gldas_2_1_noah_0_10cm", "start_date": "2015-01-15"}, "first day"),
        ({"dataset": "gldas_2_1_noah_0_10cm", "start_date": "2025-01-01"}, "before"),
        ({"dataset": "gldas_2_1_noah_0_10cm", "start_date": "1990-01-01"}, "exceeds"),
    ],
)
def test_invalid_requests_return_422(params, fragment) -> None:
    r = make_client().get("/api/v1/soil-moisture", params={**Q, **params})
    assert r.status_code == 422
    assert fragment in str(r.json()["detail"])


def test_unsupported_location_returns_422_with_reason() -> None:
    r = make_client().get("/api/v1/soil-moisture", params={
        **Q, "dataset": "gldas_2_1_noah_0_10cm", "latitude": -75})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "outside_dataset_coverage"


def test_provider_errors_map_to_502_and_engine_errors_to_503() -> None:
    def bad(*a):
        return "garbage"
    r = make_client(gldas=bad).get("/api/v1/soil-moisture", params={**Q, "dataset": "gldas_2_1_noah_0_10cm"})
    assert r.status_code == 502

    def fail(*a):
        raise EarthEngineInitializationError("Earth Engine initialization failed")
    r = make_client(gldas=fail).get("/api/v1/soil-moisture", params={**Q, "dataset": "gldas_2_1_noah_0_10cm"})
    assert r.status_code == 503


def test_compare_is_descriptive_and_never_merged() -> None:
    r = make_client().get("/api/v1/soil-moisture/compare", params={
        **Q, "datasets": "gldas_2_1_noah_0_10cm,smap_l3e_v006_am", "start_date": "2016-01-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["datasets_are_merged"] is False
    assert set(body["results"]) == {"gldas_2_1_noah_0_10cm", "smap_l3e_v006_am"}
    (pair,) = body["descriptive_agreement"]["pairs"]
    assert pair["common_valid_months"] >= 36
    assert pair["mean_difference_m3_m3"] is not None
    assert pair["monthly_anomaly_spearman_rho"] is not None
    assert "not error" in pair["mean_difference_label"]
    assert body["descriptive_agreement"]["inferential_test_of_slope_difference"] is None
    assert any(t.startswith("depth:") for t in body["differences"])
    flat = str({k: v for k, v in body.items() if k != "results"}).lower()
    assert "merged_series" not in flat and "best_estimate" not in flat and "average_of" not in flat


def test_compare_between_smap_versions_notes_version_difference() -> None:
    body = make_client().get("/api/v1/soil-moisture/compare", params={
        **Q, "datasets": "smap_l3e_v005_am,smap_l3e_v006_am", "start_date": "2016-01-01", "end_date": "2023-01-01"}).json()
    assert any(t.startswith("version:") for t in body["differences"])
    assert not any(t.startswith("depth:") for t in body["differences"])


def test_compare_excludes_frozen_gldas_months() -> None:
    body = make_client(gldas=gldas_loader(tsoil=260.0)).get("/api/v1/soil-moisture/compare", params={
        **Q, "datasets": "gldas_2_1_noah_0_10cm,smap_l3e_v006_am", "start_date": "2016-01-01"}).json()
    assert body["descriptive_agreement"]["excluded_frozen_months"] > 0
    assert body["descriptive_agreement"]["pairs"][0]["common_valid_months"] == 0


@pytest.mark.parametrize("datasets", ["gldas_2_1_noah_0_10cm", "smap_l3e_v005_am,smap_l3e_v005_am",
                                      "a,b,c,d"])
def test_compare_rejects_bad_dataset_lists(datasets) -> None:
    r = make_client().get("/api/v1/soil-moisture/compare", params={**Q, "datasets": datasets})
    assert r.status_code == 422


def test_openapi_lists_soil_moisture_paths() -> None:
    paths = make_client().get("/openapi.json").json()["paths"]
    for p in ("/api/v1/soil-moisture/datasets", "/api/v1/soil-moisture",
              "/api/v1/soil-moisture/trend", "/api/v1/soil-moisture/compare"):
        assert p in paths
