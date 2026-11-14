"""NASA POWER daily request windowing (Phase 1, fix 2).

The application setting ``power_window_years`` controls how many calendar years each
daily POWER request spans. These tests pin the default, the configuration rollback,
request counts and boundaries, and that 1-year and 10-year windows give identical
service outputs for temperature, relative humidity and extreme heat.
"""

from datetime import date, timedelta
import math

import httpx
import pytest

from app.core.config import Settings
from app.extremes.hot_days import HotDayPolicy
from app.main import create_app
from app.power.client import PowerClient, PowerRateLimitError, PowerResponseError
from app.power.models import PowerParameter, PowerPointQuery
from app.services.extreme_heat_service import ExtremeHeatService
from app.services.relative_humidity_service import RelativeHumidityService
from app.services.temperature_service import TemperatureService

FILL = -999.0
UNITS = {"T2M": "C", "T2M_MAX": "C", "RH2M": "%"}


def _series(param: str, start: date, end: date) -> dict[str, float]:
    """Deterministic daily values with periodic fill values and absent days."""
    values: dict[str, float] = {}
    day, index = start, 0
    while day < end:
        index += 1
        if index % 401 == 0:
            day += timedelta(days=1)
            continue  # absent from the response
        if index % 397 == 0:
            values[day.strftime("%Y%m%d")] = FILL
        elif param == "RH2M":
            values[day.strftime("%Y%m%d")] = round(60 + 20 * math.sin(index / 29.0), 2)
        else:
            base = 31.0 if param == "T2M_MAX" else 26.0
            values[day.strftime("%Y%m%d")] = round(base + 5 * math.sin(index / 58.1) + 0.0001 * index, 2)
        day += timedelta(days=1)
    return values


DATA = {param: _series(param, date(1981, 1, 1), date(2026, 1, 1)) for param in UNITS}


class MockPower:
    """Serves DATA like the POWER daily point endpoint and records each request."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        param = params["parameters"]
        values = {k: v for k, v in DATA[param].items() if params["start"] <= k <= params["end"]}
        return httpx.Response(200, json={
            "header": {"time_standard": params["time-standard"], "fill_value": FILL},
            "properties": {"parameter": {param: values}},
            "parameters": {param: {"units": UNITS[param]}},
        })


def _client(window_years: int, server: MockPower | None = None) -> tuple[PowerClient, MockPower]:
    server = server or MockPower()
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(server)), window_years=window_years)
    return client, server


# --- configuration -------------------------------------------------------------


def test_default_power_window_is_ten_years() -> None:
    assert Settings(_env_file=None).power_window_years == 10


def test_power_window_can_be_rolled_back_through_configuration(monkeypatch) -> None:
    monkeypatch.setenv("POWER_WINDOW_YEARS", "1")
    assert Settings(_env_file=None).power_window_years == 1


@pytest.mark.parametrize("value", ["0", "11"])
def test_power_window_stays_within_validated_bounds(monkeypatch, value) -> None:
    monkeypatch.setenv("POWER_WINDOW_YEARS", value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


@pytest.mark.parametrize("window", [1, 10])
def test_application_wires_the_setting_into_every_power_service(window) -> None:
    app = create_app(Settings(_env_file=None, power_window_years=window))
    for name in ("relative_humidity_service", "temperature_service", "extreme_heat_service"):
        assert getattr(app.state, name)._client._window_years == window


def test_power_client_constructor_default_is_unchanged() -> None:
    assert PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(MockPower())))._window_years == 1


# --- request counts and boundaries -----------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "window", "expected"),
    [
        (date(1981, 1, 1), date(2026, 1, 1), 10, [("19810101", "19901231"), ("19910101", "20001231"), ("20010101", "20101231"), ("20110101", "20201231"), ("20210101", "20251231")]),
        (date(1991, 1, 1), date(2021, 1, 1), 10, [("19910101", "20001231"), ("20010101", "20101231"), ("20110101", "20201231")]),
        (date(2015, 7, 15), date(2021, 3, 2), 10, [("20150715", "20210301")]),
        (date(2015, 6, 1), date(2026, 1, 1), 10, [("20150601", "20241231"), ("20250101", "20251231")]),
        (date(2016, 2, 28), date(2016, 3, 2), 10, [("20160228", "20160301")]),
        (date(2015, 7, 15), date(2017, 3, 2), 1, [("20150715", "20151231"), ("20160101", "20161231"), ("20170101", "20170301")]),
    ],
)
def test_daily_windows_follow_calendar_year_boundaries(start, end, window, expected) -> None:
    client, server = _client(window)
    client.fetch_daily_point(PowerPointQuery(0, 0, start, end, "LST"), PowerParameter.T2M)
    assert [(r["start"], r["end"]) for r in server.requests] == expected
    assert all(r["time-standard"] == "LST" and r["parameters"] == "T2M" and r["community"] == "AG" for r in server.requests)


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(1981, 1, 1), date(2026, 1, 1)), (date(2015, 7, 15), date(2021, 3, 2)), (date(2019, 12, 31), date(2020, 3, 1))],
)
@pytest.mark.parametrize("param", [PowerParameter.T2M, PowerParameter.RH2M, PowerParameter.T2M_MAX])
def test_one_and_ten_year_windows_return_identical_payloads(start, end, param) -> None:
    query = PowerPointQuery(0, 0, start, end, "LST")
    one = _client(1)[0].fetch_daily_point(query, param)
    ten = _client(10)[0].fetch_daily_point(query, param)
    assert ten == one
    assert list(ten.values) == sorted(ten.values)
    assert ten.units == UNITS[param.value] and ten.fill_value == FILL and ten.time_standard == "LST"


def test_ten_year_window_still_rejects_data_outside_the_window() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"properties": {"parameter": {"T2M": {"20300101": 20.0}}}, "parameters": {"T2M": {"units": "C"}}})

    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)), window_years=10)
    with pytest.raises(PowerResponseError, match="outside the requested window"):
        client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1)), PowerParameter.T2M)


def test_ten_year_window_still_rejects_unit_changes_between_windows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        unit = "C" if request.url.params["start"].startswith("2000") else "K"
        start = request.url.params["start"]
        return httpx.Response(200, json={"properties": {"parameter": {"T2M": {start: 20.0}}}, "parameters": {"T2M": {"units": unit}}})

    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)), window_years=10)
    with pytest.raises(PowerResponseError, match="units changed"):
        client.fetch_daily_point(PowerPointQuery(0, 0, date(2000, 1, 1), date(2012, 1, 1)), PowerParameter.T2M)


def test_ten_year_window_preserves_rate_limit_error() -> None:
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429, json={}))), window_years=10)
    with pytest.raises(PowerRateLimitError):
        client.fetch_daily_point(PowerPointQuery(0, 0, date(2000, 1, 1), date(2012, 1, 1)), PowerParameter.T2M)


# --- service-level equivalence -------------------------------------------------------


QUERY_10Y = PowerPointQuery(16.8661, 96.1951, date(2016, 1, 1), date(2026, 1, 1), "LST")
QUERY_PARTIAL = PowerPointQuery(16.8661, 96.1951, date(2015, 7, 15), date(2021, 3, 2), "LST")


@pytest.mark.parametrize("query", [QUERY_10Y, QUERY_PARTIAL])
def test_temperature_outputs_identical_for_one_and_ten_year_windows(query) -> None:
    one, ten = (TemperatureService(_client(w)[0]).analyze(query) for w in (1, 10))
    assert ten == one
    assert ten.series.missing_dates and ten.trend.theil_sen is not None


@pytest.mark.parametrize("query", [QUERY_10Y, QUERY_PARTIAL])
def test_relative_humidity_outputs_identical_for_one_and_ten_year_windows(query) -> None:
    one, ten = (RelativeHumidityService(_client(w)[0]).analyze(query) for w in (1, 10))
    assert ten == one
    assert ten.series.missing_dates and ten.trend.theil_sen is not None


def test_extreme_heat_outputs_identical_for_one_and_ten_year_windows() -> None:
    policy = HotDayPolicy(reference_start_year=2011, reference_end_year=2020, minimum_window_fraction=0.7)
    query = PowerPointQuery(16.8661, 96.1951, date(2019, 1, 1), date(2022, 1, 1), "LST")
    servers = {w: MockPower() for w in (1, 10)}
    results = {w: ExtremeHeatService(_client(w, servers[w])[0], policy).analyze(query) for w in (1, 10)}
    assert results[10] == results[1]
    assert len(servers[1].requests) == 10 + 3 and len(servers[10].requests) == 1 + 1
    assert any(s.bootstrap_adjusted_percentage is not None for s in results[10].annual_summaries)
