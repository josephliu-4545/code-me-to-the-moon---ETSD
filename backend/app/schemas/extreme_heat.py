from typing import Any
from pydantic import BaseModel


class ExtremeHeatResponse(BaseModel):
    variable: str
    dataset: str
    parameter: str
    units: dict[str, str]
    time_standard: str
    location: dict[str, Any]
    period: dict[str, Any]
    reference_period: dict[str, Any]
    methodology: dict[str, Any]
    annual_summaries: list[dict[str, Any]]
    trend_basis: str
    limitations: list[str]
    trend: dict[str, Any] | None = None
