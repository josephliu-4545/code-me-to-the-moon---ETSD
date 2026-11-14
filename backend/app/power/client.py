from datetime import date, timedelta
from typing import Any

import httpx

from app.power.models import PowerParameter, PowerPayload, PowerPointQuery


class PowerClientError(RuntimeError):
    pass


class PowerRateLimitError(PowerClientError):
    pass


class PowerTimeoutError(PowerClientError):
    pass


class PowerUpstreamValidationError(PowerClientError):
    pass


class PowerResponseError(PowerClientError):
    pass


class PowerClient:
    def __init__(
        self,
        http_client: httpx.Client | None = None,
        base_url: str = "https://power.larc.nasa.gov/api/temporal",
        timeout_seconds: float = 30.0,
        window_years: int = 1,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout_seconds)
        self._base_url = base_url.rstrip("/")
        self._window_years = window_years

    def fetch_daily_point(self, query: PowerPointQuery, parameter: PowerParameter = PowerParameter.RH2M) -> PowerPayload:
        windows: list[tuple[date, date]] = []
        cursor = query.start_date
        while cursor < query.end_date:
            boundary = date(cursor.year + self._window_years, 1, 1)
            window_end = min(boundary, query.end_date)
            windows.append((cursor, window_end))
            cursor = window_end
        return self._merge(self._request_daily(query, start, end, parameter) for start, end in windows)

    def fetch_monthly_point(self, query: PowerPointQuery, parameter: PowerParameter = PowerParameter.RH2M) -> PowerPayload:
        params = self._base_params(query, parameter)
        params.update({"start": str(query.start_date.year), "end": str((query.end_date - timedelta(days=1)).year)})
        return self._request("monthly", params, parameter)

    def _request_daily(self, query: PowerPointQuery, start: date, end: date, parameter: PowerParameter) -> PowerPayload:
        params = self._base_params(query, parameter)
        params.update({
            "start": start.strftime("%Y%m%d"),
            "end": (end - timedelta(days=1)).strftime("%Y%m%d"),
            "time-standard": query.time_standard,
        })
        payload = self._request("daily", params, parameter)
        for key in payload.values:
            try:
                item_date = date.fromisoformat(f"{key[:4]}-{key[4:6]}-{key[6:8]}")
            except (ValueError, TypeError):
                raise PowerResponseError("POWER returned an invalid daily date") from None
            if not start <= item_date < end:
                raise PowerResponseError("POWER returned data outside the requested window")
        return payload

    def _base_params(self, query: PowerPointQuery, parameter: PowerParameter) -> dict[str, str | float]:
        return {
            "parameters": parameter.value,
            "community": "AG",
            "longitude": query.longitude,
            "latitude": query.latitude,
            "format": "JSON",
        }

    def _request(self, temporal: str, params: dict[str, Any], parameter: PowerParameter) -> PowerPayload:
        try:
            response = self._client.get(f"{self._base_url}/{temporal}/point", params=params)
        except httpx.TimeoutException as exc:
            raise PowerTimeoutError("NASA POWER request timed out") from exc
        except httpx.HTTPError as exc:
            raise PowerClientError("NASA POWER request failed") from exc
        if response.status_code == 429:
            raise PowerRateLimitError("NASA POWER rate limit exceeded")
        if response.status_code == 422:
            raise PowerUpstreamValidationError("NASA POWER rejected the request")
        if not response.is_success:
            raise PowerClientError("NASA POWER returned an HTTP error")
        try:
            body = response.json()
            values = body["properties"]["parameter"][parameter.value]
            metadata = body.get("parameters", {}).get(parameter.value, {})
            if not isinstance(values, dict):
                raise TypeError
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise PowerResponseError("NASA POWER response is malformed") from exc
        header = body.get("header", {})
        return PowerPayload(
            dict(values),
            metadata.get("units"),
            metadata.get("fill_value", header.get("fill_value")),
            header.get("time_standard"),
            parameter,
        )

    @staticmethod
    def _merge(payloads: Any) -> PowerPayload:
        merged: dict[str, object] = {}
        units: str | None = None
        fill: object | None = None
        time_standard: str | None = None
        parameter: PowerParameter | None = None
        for payload in payloads:
            if parameter is not None and payload.parameter != parameter:
                raise PowerResponseError("NASA POWER parameter changed between windows")
            parameter = payload.parameter
            if units is not None and payload.units != units:
                raise PowerResponseError("NASA POWER units changed between windows")
            units = payload.units
            fill = payload.fill_value if fill is None else fill
            if time_standard is not None and payload.time_standard not in {None, time_standard}:
                raise PowerResponseError("NASA POWER time standard changed between windows")
            time_standard = payload.time_standard or time_standard
            for key, value in payload.values.items():
                if key in merged and merged[key] != value:
                    raise PowerResponseError("NASA POWER returned conflicting duplicate data")
                merged[key] = value
        return PowerPayload(dict(sorted(merged.items())), units, fill, time_standard, parameter or PowerParameter.RH2M)
