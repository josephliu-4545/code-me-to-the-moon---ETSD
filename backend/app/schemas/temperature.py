from typing import Any
from pydantic import BaseModel


class TemperatureResponse(BaseModel):
    variable: str
    dataset: str
    parameter: str
    units: str
    time_standard: str
    location: dict[str, Any]
    period: dict[str, Any]
    temporal_resolution: str
    observations: list[dict[str, Any]]
    coverage: dict[str, Any]


class TemperatureTrendResponse(BaseModel):
    variable: str
    dataset: str
    parameter: str
    units: str
    time_standard: str
    location: dict[str, Any]
    period: dict[str, Any]
    annual_summaries: list[dict[str, Any]]
    trend: dict[str, Any]
    methodology: dict[str, Any]
    limitations: list[str]
