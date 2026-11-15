"""Regression tests use real middleware, routing and services; only providers are synthetic."""
from datetime import date
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner
from app.power.models import PowerParameter, PowerPayload
from app.services.temperature_service import TemperatureService
from app.api.routes.unified import _power_cell


class Provider:
    def fetch_daily_point(self, query, parameter):
        assert parameter == PowerParameter.T2M
        return PowerPayload({"20200101": 25.0}, "C", -999, "LST", parameter)


def test_authenticated_unified_path_and_openapi():
    runner = BoundedOperationRunner(1)
    app = create_app(Settings(_env_file=None, api_keys="test-only-key"),
                     temperature_service=TemperatureService(Provider()), power_operation_runner=runner)
    q = dict(variable="temperature", latitude=16.8, longitude=96.1,
             start_date="2020-01-01", end_date="2021-01-01")
    try:
        with TestClient(app) as c:
            assert c.get("/api/v2/analysis", params=q).status_code == 401
            assert c.get("/api/v2/analysis", params=q, headers={"X-API-Key": "wrong"}).status_code == 401
            r = c.get("/api/v2/analysis", params=q, headers={"X-API-Key": "test-only-key"})
            assert r.status_code == 200, r.text
            a = r.json()
            assert a["trend"]["slope"] is None
            assert a["investigation"]["method"] == "theil_sen"
            again = c.get("/api/v2/analysis", params=q, headers={"X-API-Key": "test-only-key"}).json()
            assert again["investigation"]["id"] == a["investigation"]["id"]
            assert again["investigation"]["provenance_status"] == "cached_nasa_retrieval"
            schema = app.openapi()["paths"]["/api/v2/analysis"]["get"]
            assert schema["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("UnifiedAnalysisResponse")
    finally:
        runner.shutdown()


def test_catalog_uses_product_registry_and_actual_region_settings():
    app = create_app(Settings(_env_file=None, precipitation_region_max_span_degrees=2,
                              precipitation_region_min_valid_area_fraction=.8))
    with TestClient(app) as c:
        catalog = {v["id"]: v for v in c.get("/api/v2/variables").json()["variables"]}
    assert len(catalog) == 6
    assert catalog["precipitation"]["max_region_span_degrees"] == 2
    assert "80%" in catalog["precipitation"]["region_description"]
    products = {p["key"]: p for p in catalog["soil_moisture"]["products"]}
    assert products["smap_l3e_v005_am"]["availability"]["documented_last"] == "2023-12-02"
    assert products["smap_l3e_v005_am"]["availability"]["latest_complete_year"] == 2022
    assert products["smap_l3e_v006_am"]["availability"]["latest_observation"] is None
    assert products["smap_l3e_v006_am"]["availability"]["verification"] == "documented_only"


def test_power_approximation_never_extends_beyond_world():
    for lat, lon in [(90,180),(-90,-180)]:
        cell = _power_cell(lat,lon)
        assert cell["approximate"]
        b = cell["bounds"]
        assert -90 <= b["south"] < b["north"] <= 90
        assert -180 <= b["west"] < b["east"] <= 180
