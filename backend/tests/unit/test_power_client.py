from datetime import date

import httpx
import pytest

from app.power.client import (
    PowerClient,
    PowerRateLimitError,
    PowerResponseError,
)
from app.power.models import PowerParameter, PowerPointQuery


def _response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_daily_request_translates_half_open_dates_and_requests_lst() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response({"properties": {"parameter": {"RH2M": {"20200228": 70.0, "20200229": 71.0}}}, "parameters": {"RH2M": {"units": "%"}}})

    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.fetch_daily_point(PowerPointQuery(16.8661, 96.1951, date(2020, 2, 28), date(2020, 3, 1), "LST"))

    params = requests[0].url.params
    assert params["start"] == "20200228"
    assert params["end"] == "20200229"
    assert params["time-standard"] == "LST"
    assert params["parameters"] == "RH2M"
    assert result.values == {"20200228": 70.0, "20200229": 71.0}


def test_daily_request_splits_years_and_merges_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params["start"]
        payload = {"20201231": 60.0} if start.startswith("2020") else {"20210101": 61.0}
        return _response({"properties": {"parameter": {"RH2M": payload}}, "parameters": {"RH2M": {"units": "%"}}})

    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 12, 31), date(2021, 1, 2), "UTC"))
    assert list(result.values) == ["20201231", "20210101"]


def test_rate_limit_has_specific_error() -> None:
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda _: _response({}, 429))))
    with pytest.raises(PowerRateLimitError):
        client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2), "LST"))


def test_conflicting_duplicate_values_are_rejected() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        value = 60.0 if calls == 1 else 61.0
        return _response({"properties": {"parameter": {"RH2M": {"20200101": value}}}, "parameters": {"RH2M": {"units": "%"}}})

    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)), window_years=1)
    query = PowerPointQuery(0, 0, date(2020, 1, 1), date(2022, 1, 1), "LST")
    with pytest.raises(PowerResponseError):
        client.fetch_daily_point(query)


def test_response_preserves_actual_time_standard() -> None:
    payload = {"header": {"time_standard": "LST"}, "properties": {"parameter": {"RH2M": {"20200101": 50}}}, "parameters": {"RH2M": {"units": "%"}}}
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda _: _response(payload))))
    result = client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2), "LST"))
    assert result.time_standard == "LST"


def test_parameter_allow_list_requests_and_parses_t2m() -> None:
    seen: list[str] = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["parameters"])
        return _response({"properties": {"parameter": {"T2M": {"20200101": 25.5}}}, "parameters": {"T2M": {"units": "C"}}, "header": {"time_standard": "LST"}})
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2)), PowerParameter.T2M)
    assert seen == ["T2M"]
    assert result.parameter == PowerParameter.T2M
    assert result.values["20200101"] == 25.5


def test_parameter_mismatch_is_rejected() -> None:
    body = {"properties": {"parameter": {"RH2M": {"20200101": 50}}}, "parameters": {"RH2M": {"units": "%"}}}
    client = PowerClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda _: _response(body))))
    with pytest.raises(PowerResponseError):
        client.fetch_daily_point(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2)), PowerParameter.T2M)
