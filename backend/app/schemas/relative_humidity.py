from datetime import date
from typing import Any, Literal

from pydantic import BaseModel


class RelativeHumidityObservationResponse(BaseModel):
    period_start: date
    period_end: date
    relative_humidity_percent: float


class RelativeHumidityResponse(BaseModel):
    variable: str = "Relative Humidity"
    dataset: str = "NASA POWER"
    parameter: str = "RH2M"
    units: str = "%"
    temporal_resolution: Literal["daily", "monthly"]
    time_standard: Literal["LST", "UTC"]
    location: dict[str, Any]
    period: dict[str, date]
    observations: list[RelativeHumidityObservationResponse]
    coverage: dict[str, Any]
    methodology: dict[str, Any]
    limitations: list[str]


class RelativeHumidityTrendResponse(BaseModel):
    variable: str = "Relative Humidity"
    dataset: str = "NASA POWER"
    parameter: str = "RH2M"
    units: str = "%"
    time_standard: Literal["LST"] = "LST"
    location: dict[str, Any]
    period: dict[str, date]
    annual_summaries: list[dict[str, Any]]
    trend: dict[str, Any]
    coverage_policy: dict[str, Any]
    methodology: dict[str, Any]
    limitations: list[str]
