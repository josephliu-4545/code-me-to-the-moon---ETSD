"""/api/v2 trend checks added on top of the shared engine: the sudden-step check (all
variables) and the seasonal NDVI trend. Upstream v1 bodies come from the live Yangon
fixture used by test_unified_api.py."""

import copy

import pytest
from fastapi.testclient import TestClient

from app.api.routes import unified
from app.core.config import Settings
from app.main import create_app
from tests.unit.test_unified_api import FIXTURE, Q

NOISE = [0.12, -0.08, 0.15, -0.11, 0.03, -0.14, 0.09, -0.02, 0.06, -0.13, 0.1, -0.05,
         0.14, -0.09, 0.01, -0.12, 0.08, -0.03, 0.11, -0.07, 0.04, -0.1, 0.13, -0.06]


@pytest.fixture
def client():
    return TestClient(create_app(Settings(_env_file=None, ee_project_id="test")))


def _serve(monkeypatch, body):
    async def fake(request, path, params):
        return body
    monkeypatch.setattr(unified, "_call_v1", fake)


def _temperature_with(values: dict[int, float]) -> dict:
    """The live temperature body, re-dated to the given years with the given annual means."""
    body = copy.deepcopy(FIXTURE["temperature_trend"])
    template = body["annual_summaries"][0]
    body["annual_summaries"] = [{**copy.deepcopy(template), "year": y, "annual_value": v} for y, v in values.items()]
    body["trend"]["eligible_years"] = list(values)
    return body


def test_step_in_long_record_is_flagged(client, monkeypatch) -> None:
    years = range(2001, 2025)
    _serve(monkeypatch, _temperature_with({y: (29.0 if y <= 2007 else 27.5) + n for y, n in zip(years, NOISE)}))
    cp = client.get("/api/v2/analysis", params={**Q, "variable": "temperature", "start_date": "2001-01-01"}).json()["trend"]["change_point"]
    assert cp["status"] == "step_detected"
    assert (cp["last_year_before"], cp["first_year_after"]) == (2007, 2008)
    assert cp["shift"] == pytest.approx(-1.5, abs=0.15)


def test_smooth_trend_is_not_flagged(client, monkeypatch) -> None:
    years = range(2001, 2025)
    _serve(monkeypatch, _temperature_with({y: 27 + 0.05 * (y - 2001) + n / 10 for y, n in zip(years, NOISE)}))
    cp = client.get("/api/v2/analysis", params={**Q, "variable": "temperature", "start_date": "2001-01-01"}).json()["trend"]["change_point"]
    assert cp["status"] == "none"


def test_live_yangon_decade_has_no_step(client, monkeypatch) -> None:
    _serve(monkeypatch, FIXTURE["temperature_trend"])
    cp = client.get("/api/v2/analysis", params={**Q, "variable": "temperature"}).json()["trend"]["change_point"]
    # Ten years cannot reach Pettitt p < 0.05 even for a perfect step (best case about 0.066).
    assert cp["status"] == "none"
    assert cp["pettitt_p_value"] > 0.05


def test_ndvi_uses_seasonal_kendall_on_live_yangon(client, monkeypatch) -> None:
    _serve(monkeypatch, FIXTURE["ndvi_trend"])
    body = client.get("/api/v2/analysis", params={**Q, "variable": "ndvi", "mode": "region", "radius_km": 5}).json()
    t = body["trend"]
    # The annual method finds no eligible year here (monsoon cloud); the seasonal method still estimates a trend.
    assert body["coverage"]["eligible_years"] == 0
    assert t["method"] == "seasonal_kendall"
    assert t["result_level"] == "statistical_inference"
    assert t["mann_kendall"]["direction"] == "increasing"
    assert t["slope"] == pytest.approx(0.0063467, rel=1e-3)
    assert t["slope_units"] == "NDVI units/year"
    assert t["months_used"] == [1, 2, 3, 4, 11, 12]
    assert t["sample_count"] == 60
    assert t["change_point"]["status"] in {"none", "step_detected"}
    assert body["methodology"]["trend_method"]["significance"].startswith("two-sided Seasonal Kendall")
    assert any("Jan, Feb, Mar, Apr, Nov, Dec" in item for item in body["limitations"])
    assert body["caveats"][0].startswith("Seasonal Kendall treats months as independent")
    assert "Theil-Sen" not in body["caveats"][1] and body["caveats"][1].startswith("The seasonal Sen slope")
    assert body["units"]["annual_value"] == "NDVI units"
    assert "radius_km" not in body["spatial_support"]["resolution"]


def test_other_variables_keep_the_annual_method(client, monkeypatch) -> None:
    _serve(monkeypatch, FIXTURE["temperature_trend"])
    t = client.get("/api/v2/analysis", params={**Q, "variable": "temperature"}).json()["trend"]
    assert "method" not in t and "months_used" not in t
