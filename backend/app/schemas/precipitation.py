from typing import Any

from pydantic import BaseModel


class PrecipitationResponse(BaseModel):
    variable: str
    dataset: dict[str, Any]
    location: dict[str, Any]
    spatial_support: dict[str, Any]
    period: dict[str, Any]
    temporal_resolution: str
    units: dict[str, str]
    monthly_observations: list[dict[str, Any]]
    annual_summaries: list[dict[str, Any]]
    coverage: dict[str, Any]
    methodology: dict[str, Any]
    limitations: list[str]


class PrecipitationTrendResponse(PrecipitationResponse):
    trend: dict[str, Any]
    relative_change: dict[str, Any] | None = None

