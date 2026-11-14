"""Opt-in real-data validation for IMERG V07 precipitation at Yangon."""

from dataclasses import asdict
from datetime import date
import json
import os

from app.core.earth_engine import EarthEngineManager
from app.precipitation.models import PrecipitationQuery
from app.services.imerg_service import ImergService
from app.services.precipitation_service import PrecipitationService


def main() -> None:
    project = os.environ["EE_PROJECT_ID"]
    manager = EarthEngineManager(project)
    query = PrecipitationQuery(16.8661, 96.1951, date(2015, 1, 1), date(2025, 1, 1))
    result = PrecipitationService(ImergService(manager)).analyze(query)

    manager.initialize()
    ee = manager.ee
    point = ee.Geometry.Point([query.longitude, query.latitude])
    comparison_start, comparison_end = "2020-06-01", "2020-07-01"
    half_hourly = (
        ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
        .filterDate(comparison_start, comparison_end)
        .filter(ee.Filter.eq("status", "permanent"))
        .select("precipitation")
    )
    half_hour_count = int(half_hourly.size().getInfo())
    half_hour_accumulation = half_hourly.map(
        lambda image: image.multiply(0.5)
    ).sum().reduceRegion(
        reducer=ee.Reducer.first(), geometry=point, scale=11132,
        bestEffort=False, maxPixels=10,
    ).get("precipitation").getInfo()
    comparison_month = next(item for item in result.series.observations if item.month == date(2020, 6, 1))
    monthly_accumulation = comparison_month.accumulation_mm
    absolute_difference = float(monthly_accumulation) - float(half_hour_accumulation)

    payload = {
        "location": {"latitude": query.latitude, "longitude": query.longitude},
        "period": {"start": query.start_date.isoformat(), "end_exclusive": query.end_date.isoformat()},
        "grid_cell": {"id": result.series.grid_cell_id, "center": result.series.grid_cell_center},
        "monthly_observations": [
            {"month": item.month.isoformat(), "mean_rate_mm_per_hour": item.mean_rate_mm_per_hour, "accumulation_mm": item.accumulation_mm}
            for item in result.series.observations
        ],
        "annual_summaries": [asdict(item) for item in result.annual_summaries],
        "eligible_years": list(result.trend.eligible_years),
        "trend": asdict(result.trend),
        "bounded_half_hourly_comparison": {
            "month": "2020-06",
            "permanent_half_hour_images": half_hour_count,
            "monthly_product_accumulation_mm": monthly_accumulation,
            "half_hourly_sum_accumulation_mm": half_hour_accumulation,
            "monthly_minus_half_hourly_mm": absolute_difference,
            "relative_difference_percent": absolute_difference / float(half_hour_accumulation) * 100,
        },
    }
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()

