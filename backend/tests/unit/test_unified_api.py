import asyncio
import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from scipy.stats import spearmanr

from app.api.routes import unified
from app.core.config import Settings
from app.main import create_app
from app.services.soil_moisture_provider import EarthEngineSoilMoistureProvider
from app.services.soil_moisture_service import SoilMoistureService
from app.soil_moisture.models import expected_slots


FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" /
                      "v1_yangon_2015_2025_live_2026-11-13.json").read_text(encoding="utf-8"))
BY_PATH = {
    "/api/v1/temperature/trend": "temperature_trend",
    "/api/v1/relative-humidity/trend": "rh_trend",
    "/api/v1/extreme-heat/trend": "heat_trend",
    "/api/v1/precipitation/trend": "precip_trend",
    "/api/v1/ndvi/trend": "ndvi_trend",
}
Q = {"latitude": 16.8661, "longitude": 96.1951, "start_date": "2015-01-01", "end_date": "2025-01-01"}


@pytest.fixture
def calls(monkeypatch):
    log = []

    async def fake(request, path, params):
        log.append((path, params))
        await asyncio.sleep(0.01)
        return FIXTURE[BY_PATH[path]]

    monkeypatch.setattr(unified, "_call_v1", fake)
    return log


@pytest.fixture
def client():
    return TestClient(create_app(Settings(_env_file=None, ee_project_id="test")))


def test_variables_catalog_lists_six_variables_with_modes(client) -> None:
    body = client.get("/api/v2/variables").json()
    ids = [v["id"] for v in body["variables"]]
    assert ids == ["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"]
    for v in body["variables"]:
        assert v["modes"]["point"] is True
        if not v["modes"]["region"]:
            assert v["region_unsupported_reason"]
        assert "v1" not in v and "v1_region" not in v and v["max_years"] >= 1
    assert body["caveats"][0].startswith("Mann-Kendall significance")


@pytest.mark.parametrize(
    "variable, fixture, units, series_len",
    [
        ("temperature", "temperature_trend", "°C", 120),
        ("relative_humidity", "rh_trend", "%", 120),
        ("extreme_heat", "heat_trend", "% of days", 0),
        ("precipitation", "precip_trend", "mm/year", 120),
    ],
)
def test_analysis_normalises_each_variable(client, calls, variable, fixture, units, series_len) -> None:
    body = client.get("/api/v2/analysis", params={**Q, "variable": variable}).json()
    source = FIXTURE[fixture]
    assert body["variable"]["id"] == variable
    assert body["units"]["annual_value"] == units
    assert len(body["annual"]) == 10
    assert len(body["series"]) == series_len
    assert body["trend"]["slope"] == pytest.approx(source["trend"]["theil_sen"]["slope"])
    assert body["trend"]["result_level"] == source["trend"]["result_level"]
    assert body["caveats"][0] == unified.INFERENCE_CAVEAT
    assert body["data_status"] == "live_nasa_retrieval"
    assert body["cache"]["hit"] is False


def test_extreme_heat_keeps_its_own_definition(client, calls) -> None:
    body = client.get("/api/v2/analysis", params={**Q, "variable": "extreme_heat"}).json()
    first = FIXTURE["heat_trend"]["annual_summaries"][0]
    assert body["annual"][0]["value"] == first["primary_trend_percentage"]
    assert body["annual"][0]["extra"]["raw_hot_day_count"] == first["raw_hot_day_count"]
    assert body["extra"]["reference_period"]["start_year"] == 1991


def test_precipitation_reports_native_cell_bounds(client, calls) -> None:
    s = client.get("/api/v2/analysis", params={**Q, "variable": "precipitation"}).json()["spatial_support"]
    assert s["type"] == "native_grid_cell" and s["cell"]["approximate"] is False
    b = s["cell"]["bounds"]
    assert b["south"] <= 16.8661 < b["north"] and b["west"] <= 96.1951 < b["east"]


def test_power_variables_report_approximate_cell(client, calls) -> None:
    s = client.get("/api/v2/analysis", params={**Q, "variable": "temperature"}).json()["spatial_support"]
    assert s["type"] == "grid_cell_estimate" and s["cell"]["approximate"] is True
    assert s["cell"]["center"] == [17.0, 96.25]


def test_ndvi_point_and_region_radii(client, calls) -> None:
    client.get("/api/v2/analysis", params={**Q, "variable": "ndvi"})
    client.get("/api/v2/analysis", params={**Q, "variable": "ndvi", "mode": "region"})
    client.get("/api/v2/analysis", params={**Q, "variable": "ndvi", "mode": "region", "radius_km": 20})
    assert [c[1]["radius_km"] for c in calls] == [0.25, 5, 20]


def test_results_are_cached_and_labelled(client, calls) -> None:
    first = client.get("/api/v2/analysis", params={**Q, "variable": "temperature"}).json()
    second = client.get("/api/v2/analysis", params={**Q, "variable": "temperature"}).json()
    assert len(calls) == 1
    assert second["cache"]["hit"] is True
    assert second["data_status"] == "cached_nasa_retrieval"
    assert second["cache"]["retrieved_at"] == first["cache"]["retrieved_at"]


def test_concurrent_identical_requests_share_one_retrieval(calls) -> None:
    app = create_app(Settings(_env_file=None, ee_project_id="test"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await asyncio.gather(*[c.get("/api/v2/analysis", params={**Q, "variable": "precipitation"})
                                          for _ in range(4)])

    responses = asyncio.run(run())
    assert all(r.status_code == 200 for r in responses)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "params, status, fragment",
    [
        ({"variable": "temperature", "mode": "region"}, 422, "region_mode_unsupported"),
        ({"variable": "temperature", "bbox": "96,16,97,17"}, 422, "bbox_unsupported"),
        ({"variable": "ndvi", "bbox": "96,16,97,17"}, 422, "radius_km"),
        ({"variable": "precipitation", "bbox": "96,16,97"}, 422, "west,south,east,north"),
        ({"variable": "temperature", "radius_km": 5}, 422, "radius_km"),
        ({"variable": "temperature", "dataset": "x"}, 422, "dataset"),
        ({"variable": "temperature", "start_date": "2025-01-01"}, 422, "before"),
        ({"variable": "unknown"}, 422, ""),
    ],
)
def test_invalid_requests(client, calls, params, status, fragment) -> None:
    r = client.get("/api/v2/analysis", params={**Q, **params})
    assert r.status_code == status
    assert fragment in json.dumps(r.json())
    assert calls == []


def test_upstream_errors_keep_their_status(client, monkeypatch) -> None:
    async def fail(request, path, params):
        raise HTTPException(503, "Earth Engine is busy; retry later")
    monkeypatch.setattr(unified, "_call_v1", fail)
    r = client.get("/api/v2/analysis", params={**Q, "variable": "precipitation"})
    assert r.status_code == 503 and "busy" in r.json()["detail"]
    # failures are not cached
    r = client.get("/api/v2/analysis", params={**Q, "variable": "precipitation"})
    assert r.status_code == 503


def test_relationships_are_descriptive_with_correct_correlations(client, calls) -> None:
    body = client.get("/api/v2/relationships", params={**Q, "variables": "temperature,relative_humidity"}).json()
    t = {s["year"]: s["annual_value"] for s in FIXTURE["temperature_trend"]["annual_summaries"]}
    h = {s["year"]: s["annual_value"] for s in FIXTURE["rh_trend"]["annual_summaries"]}
    years = sorted(t)
    assert body["common_eligible_years"] == years
    assert body["spearman_rho_annual"] == pytest.approx(spearmanr([t[y] for y in years], [h[y] for y in years]).statistic)
    dt = [t[b] - t[a] for a, b in zip(years, years[1:])]
    dh = [h[b] - h[a] for a, b in zip(years, years[1:])]
    assert body["spearman_rho_first_differences"] == pytest.approx(spearmanr(dt, dh).statistic)
    assert "does not show that one variable causes the other" in body["interpretation"]
    assert "p_value" not in json.dumps({k: v for k, v in body.items() if k != "results"})


def test_relationships_withhold_correlation_with_too_few_years(client, calls) -> None:
    body = client.get("/api/v2/relationships", params={**Q, "variables": "temperature,ndvi"}).json()
    assert body["spearman_rho_annual"] is None
    assert "fewer_than_8_common_eligible_years" in body["unavailable_reasons"]


@pytest.mark.parametrize("variables", ["temperature", "temperature,temperature", "temperature,foo"])
def test_relationships_reject_bad_variable_lists(client, calls, variables) -> None:
    assert client.get("/api/v2/relationships", params={**Q, "variables": variables}).status_code == 422


class FakeGeocodeClient:
    calls = 0
    payload: object = []
    fail = False

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        FakeGeocodeClient.calls += 1
        if FakeGeocodeClient.fail:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json=FakeGeocodeClient.payload, request=httpx.Request("GET", url))


def test_geocode_returns_results_and_caches(client, monkeypatch) -> None:
    unified._GEOCODE_CACHE.clear()
    FakeGeocodeClient.calls, FakeGeocodeClient.fail = 0, False
    FakeGeocodeClient.payload = [{"display_name": "Nairobi, Kenya", "lat": "-1.2864", "lon": "36.8172", "type": "city"},
                                 {"display_name": "bad", "lat": "x", "lon": "1"}]
    monkeypatch.setattr(unified.httpx, "AsyncClient", FakeGeocodeClient)
    body = client.get("/api/v2/geocode", params={"q": "Nairobi"}).json()
    assert body["results"] == [{"name": "Nairobi, Kenya", "latitude": -1.2864, "longitude": 36.8172, "type": "city"}]
    client.get("/api/v2/geocode", params={"q": "nairobi"})
    assert FakeGeocodeClient.calls == 1


def test_geocode_failure_is_a_clear_502(client, monkeypatch) -> None:
    unified._GEOCODE_CACHE.clear()
    FakeGeocodeClient.fail = True
    monkeypatch.setattr(unified.httpx, "AsyncClient", FakeGeocodeClient)
    r = client.get("/api/v2/geocode", params={"q": "Atlantis"})
    assert r.status_code == 502 and "coordinates" in r.json()["detail"]


# --- soil moisture through the real v1 route ---------------------------------------


class FakeManager:
    ee = None

    def initialize(self) -> None:
        pass


def _gldas(d, cell, s, e):
    rows, m = [], s
    while m < e:
        n = expected_slots(d, m)
        rows.append([m.isoformat(), n, n, n, n, n, 25.0 + 0.2 * (m.year - 2015) + 0.03 * (m.year % 3), 290.0])
        m = (m + timedelta(days=32)).replace(day=1)
    return rows


def test_soil_moisture_through_v1_route() -> None:
    provider = EarthEngineSoilMoistureProvider(
        FakeManager(), gldas_loader=_gldas, smap_loader=lambda *a: {"images": [], "rows": []},
        availability_loader=lambda d: ["2000-01-01", "2026-10-15"], neighbourhood_loader=lambda *a: 9)
    app = create_app(Settings(_env_file=None, ee_project_id="test"),
                     soil_moisture_service=SoilMoistureService(provider))
    body = TestClient(app).get("/api/v2/analysis", params={**Q, "variable": "soil_moisture"}).json()
    assert body["dataset"]["key"] == "gldas_2_1_noah_0_10cm"
    assert body["units"]["annual_value"] == "kg m-2"
    assert body["spatial_support"]["cell_status"] == "ok"
    assert body["extra"]["derived_trend"]["slope_units"] == "m3 m-3/year"
    assert len(body["series"]) == 120
    assert body["annual"][0]["extra"]["derived_volumetric"] == pytest.approx(body["annual"][0]["value"] / 100)


REGION_BODY = {
    "spatial_support": {"type": "bbox_area_weighted_mean", "bbox": {"west": 96.0, "south": 16.6, "east": 96.4, "north": 17.0},
                        "description": "Area-weighted mean", "min_valid_area_fraction": 0.95},
    "period": {"start": "2015-01-01", "end_exclusive": "2025-01-01"},
    "monthly_coverage": [{"month": "2015-01-01", "valid_area_km2": 1888.0, "total_area_km2": 1888.0, "valid_area_fraction": 1.0, "accepted": True}],
    "annual_summaries": FIXTURE["precip_trend"]["annual_summaries"],
    "trend": FIXTURE["precip_trend"]["trend"],
    "methodology": {}, "limitations": ["regional mean"],
}


def test_precipitation_bbox_routes_to_region_endpoint(client, monkeypatch) -> None:
    seen = []

    async def fake(request, path, params):
        seen.append((path, params))
        return REGION_BODY

    monkeypatch.setattr(unified, "_call_v1", fake)
    body = client.get("/api/v2/analysis", params={**Q, "variable": "precipitation", "bbox": "96.0,16.6,96.4,17.0"}).json()
    assert seen[0][0] == "/api/v1/precipitation/region/trend"
    assert seen[0][1]["west"] == 96.0 and seen[0][1]["north"] == 17.0
    s = body["spatial_support"]
    assert s["mode"] == "region" and s["type"] == "bbox_area_weighted_mean"
    assert s["single_cell_substituted"] is False and s["region_area_km2"] == 1888.0
    assert s["bbox"] == {"south": 16.6, "north": 17.0, "west": 96.0, "east": 96.4}
    assert len(body["annual"]) == 10


def test_precipitation_region_mode_defaults_to_one_degree_box(client, monkeypatch) -> None:
    seen = []

    async def fake(request, path, params):
        seen.append(params)
        return REGION_BODY

    monkeypatch.setattr(unified, "_call_v1", fake)
    client.get("/api/v2/analysis", params={**Q, "variable": "precipitation", "mode": "region"})
    p = seen[0]
    assert p["east"] - p["west"] == pytest.approx(1.0) and p["north"] - p["south"] == pytest.approx(1.0)
