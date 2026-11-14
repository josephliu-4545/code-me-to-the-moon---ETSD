from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class PowerParameter(StrEnum):
    RH2M = "RH2M"
    T2M = "T2M"
    T2M_MAX = "T2M_MAX"


@dataclass(frozen=True)
class PowerPointQuery:
    latitude: float
    longitude: float
    start_date: date
    end_date: date
    time_standard: str = "LST"

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("coordinates are outside the supported range")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.time_standard not in {"LST", "UTC"}:
            raise ValueError("time_standard must be LST or UTC")


@dataclass(frozen=True)
class PowerPayload:
    values: dict[str, object]
    units: str | None
    fill_value: object | None = None
    time_standard: str | None = None
    parameter: PowerParameter = PowerParameter.RH2M

