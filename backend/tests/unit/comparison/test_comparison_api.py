import asyncio
from datetime import timedelta

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.api.routes import comparison, unified
from app.comparison.providers import EEMonthlyProvider, expected_samples
from app.core.config import Settings
from app.main import create_app


class FakeManager:
    ee = None

    def initialize(self) -> None:
        pass


def months(start, end):
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def ee_loader(native=300.0):
    def load(entry, cell, s, e):
        rows = []
        for m in months(s, e):
            n = expected_samples(entry, m)
            images = n if entry.method in ("subdaily_mean", "daily_sum") else 1
            value = native + 0.01 * (m.year - 2015) + 0.003 * (m.year % 3)
            rows.append([m.isoformat(), images, n, n, value, images, images])
        return rows
    return load


def primary_body(variable="temperature", units="°C", slope=0.02, offset=0.0):
    years = range(2015, 2025)
    return {
        "variable": {"id": variable, "name": "x", "description": "", "annual_value_definition": ""},
        "dataset": {"source": "NASA", "id": "x", "version": "v", "provenance": "p", "doi": None},
        "spatial_support": {"mode": "point", "type": "grid_cell_estimate", "resolution": "0.5°", "description": "", "requested": {}},
        "period": {}, "units": {"annual_value": units, "slope": f"{units}/year"},
        "annual": [{"year": y, "value": offset + 27.0 + 0.02 * (y - 2015) + 0.01 * (y % 3), "eligible": True, "reasons": []} for y in years],
        "series": [], "series_definition": None,
        "trend": {"result_level": "statistical_inference", "slope": slope, "confidence_interval": [0.0, 0.04], "slope_units": f"{units}/year"},
        "coverage": {}, "methodology": {}, "caveats": [], "limitations": [], "extra": {}, "data_status": "live_nasa_retrieval",
    }


@pytest.fixture
def client(monkeypatch):
    calls = []

    async def fake_analysis(request, **kw):
        calls.append(kw)
        if kw["variable"] == "precipitation":
            return primary_body("precipitation", "mm/year", 5.0, offset=2000.0)
        return primary_body()

    monkeypatch.setattr(unified, "analysis", fake_analysis)
    app = create_app(Settings(_env_file=None, ee_project_id="test"))
    app.state.comparison_provider = EEMonthlyProvider(FakeManager(), loader=ee_loader())
    c = TestClient(app)
    c.calls = calls
    return c


Q = {"latitude": 16.8661, "longitude": 96.1951, "start_date": "2015-01-01", "end_date": "2025-01-01"}


def test_dataset_catalog_endpoint() -> None:
    body = TestClient(create_app(Settings(_env_file=None, ee_project_id="test"))).get("/api/v2/datasets").json()
    by_var = {v["variable"]: v for v in body["variables"]}
    assert by_var["temperature"]["comparison_available"] is True
    assert [d["key"] for d in by_var["temperature"]["datasets"]][0] == "nasa_power_t2m"
    assert by_var["ndvi"]["comparison_available"] is False and by_var["ndvi"]["not_yet_available_reason"]
    assert all("crs_transform" not in d and "band" not in d for v in body["variables"] for d in v["datasets"])
    assert by_var["precipitation"]["relationships"][0]["lineage"] in {"partially_related", "independent", "same_lineage"}


def test_temperature_comparison_runs_each_dataset_independently(client) -> None:
    body = client.get("/api/v2/compare", params={**Q, "variable": "temperature",
                                                  "datasets": "nasa_power_t2m,gldas_2_1_tair,era5_land_t2m"}).json()
    assert body["datasets_are_merged"] is False
    assert body["succeeded"] == ["nasa_power_t2m", "gldas_2_1_tair", "era5_land_t2m"]
    for key in body["succeeded"]:
        res = body["results"][key]
        assert res["outcome"] in {"inference", "descriptive_only"}
        assert len(res["analysis"]["annual"]) == 10
    gldas = body["results"]["gldas_2_1_tair"]["analysis"]
    assert gldas["annual"][0]["value"] == pytest.approx(26.85, abs=0.01)
    assert gldas["units"]["annual_value"] == "°C"
    assert len(body["comparison"]["pairs"]) == 3
    assert body["comparison"]["all_numerically_comparable"] is True
    assert client.calls[0]["variable"] == "temperature"


def test_partial_failure_keeps_successful_datasets(client) -> None:
    body = client.get("/api/v2/compare", params={**Q, "latitude": 60.17, "longitude": 24.94, "variable": "precipitation",
                                                  "datasets": "gpm_imerg_v07,chirps_v2_daily"}).json()
    assert body["results"]["chirps_v2_daily"]["outcome"] == "unsupported_location"
    assert body["results"]["gpm_imerg_v07"]["analysis"] is not None
    assert body["comparison"] is None and "fewer than two" in body["comparison_unavailable_reason"]


def test_region_mode_marks_point_only_datasets_unsupported(client) -> None:
    body = client.get("/api/v2/compare", params={**Q, "variable": "precipitation", "mode": "region",
                                                  "bbox": "96,16.6,96.4,17", "datasets": "gpm_imerg_v07,era5_land_tp"}).json()
    assert body["results"]["era5_land_tp"]["outcome"] == "unsupported_mode"
    assert body["results"]["gpm_imerg_v07"]["analysis"] is not None
    assert client.calls[0]["bbox"] == "96,16.6,96.4,17"


def test_provider_errors_are_reported_per_dataset(monkeypatch, client) -> None:
    async def failing(request, **kw):
        raise HTTPException(503, "Earth Engine is busy; retry later")
    monkeypatch.setattr(unified, "analysis", failing)
    body = client.get("/api/v2/compare", params={**Q, "variable": "precipitation",
                                                  "datasets": "gpm_imerg_v07,era5_land_tp"}).json()
    assert body["results"]["gpm_imerg_v07"]["outcome"] == "provider_error"
    assert body["results"]["gpm_imerg_v07"]["http_status"] == 503
    assert body["results"]["era5_land_tp"]["analysis"] is not None


def test_outside_record(client) -> None:
    body = client.get("/api/v2/compare", params={**Q, "variable": "temperature", "start_date": "1990-01-01",
                                                  "end_date": "1995-01-01", "datasets": "nasa_power_t2m,gldas_2_1_tair"}).json()
    assert body["results"]["gldas_2_1_tair"]["outcome"] == "outside_record"


def test_no_data_outcome(client) -> None:
    def empty(entry, cell, s, e):
        return [[m.isoformat(), expected_samples(entry, m), 0, 0, None, 1, 1] for m in months(s, e)]
    client.app.state.comparison_provider = EEMonthlyProvider(FakeManager(), loader=empty)
    body = client.get("/api/v2/compare", params={**Q, "variable": "temperature", "datasets": "nasa_power_t2m,era5_land_t2m"}).json()
    assert body["results"]["era5_land_t2m"]["outcome"] == "no_data"


@pytest.mark.parametrize(
    "params, fragment",
    [
        ({"variable": "ndvi", "datasets": "a,b"}, "comparison_unavailable"),
        ({"variable": "temperature", "datasets": "nasa_power_t2m"}, "2 to 4"),
        ({"variable": "temperature", "datasets": "nasa_power_t2m,nasa_power_t2m"}, "2 to 4"),
        ({"variable": "temperature", "datasets": "nasa_power_t2m,chirps_v2_daily"}, "not in the temperature catalog"),
        ({"variable": "temperature", "datasets": "nasa_power_t2m,era5_land_t2m", "start_date": "2015-01-15"}, "first day"),
        ({"variable": "temperature", "datasets": "nasa_power_t2m,era5_land_t2m", "mode": "area"}, "mode"),
    ],
)
def test_validation(client, params, fragment) -> None:
    r = client.get("/api/v2/compare", params={**Q, **params})
    assert r.status_code == 422 and fragment in str(r.json()["detail"])


def test_earth_engine_datasets_never_run_concurrently(monkeypatch, client) -> None:
    active, peak = 0, 0

    async def tracked(request, e, *args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return primary_body()

    monkeypatch.setattr(comparison, "_analyse", tracked)
    client.get("/api/v2/compare", params={**Q, "variable": "precipitation",
                                          "datasets": "gpm_imerg_v07,chirps_v2_daily,era5_land_tp"})
    assert peak == 1
