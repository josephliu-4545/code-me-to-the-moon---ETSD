from datetime import date

from pydantic import BaseModel, Field


class NDVIQuery(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    start_date: date
    end_date: date
    radius_km: float = Field(default=5, gt=0)


class NDVILocation(BaseModel):
    latitude: float
    longitude: float
    radius_km: float


class NDVIPeriod(BaseModel):
    start: date
    end: date


class NDVIObservation(BaseModel):
    date: date
    ndvi: float


class NDVIResponse(BaseModel):
    variable: str = "NDVI"
    dataset: str = "NASA MODIS MOD13Q1.061"
    units: str = "NDVI units"
    location: NDVILocation
    period: NDVIPeriod
    observation_count: int = Field(ge=0)
    observations: list[NDVIObservation]

