"""Versioned unified API (v2) for the frontend.

It calls the existing, validated v1 endpoints in-process and returns one envelope
per variable. Each variable keeps its own definition, units and spatial support;
values are never converted into a misleading common quantity. v1 is unchanged.
"""

import asyncio
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import calendar
import math
import time
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from scipy.stats import spearmanr
from pydantic import BaseModel, ConfigDict
from app.soil_moisture.datasets import DATASETS
from app.api.routes.soil_moisture import descriptor_payload

from app.api.scientific_notes import (
    DESCRIPTIVE_SLOPE_NOTE, INFERENCE_CAVEAT, SEASONAL_DESCRIPTIVE_SLOPE_NOTE, SEASONAL_TREND_METHOD, TREND_METHOD,
)
from app.api.methods_lab import build_methods_lab
from app.core.outbound_throttle import OutboundThrottle, ThrottleBusy
from app.statistics.change_point import detect_step
from app.statistics.policies import TrendPolicy
from app.statistics.seasonal import LIMITATION as SEASONAL_LIMITATION, seasonal_trend


router = APIRouter(prefix="/api/v2", tags=["unified"])

POWER_GRID = {"latitude_step": 0.5, "longitude_step": 0.625}

VARIABLES: dict[str, dict[str, Any]] = {
    "temperature": {
        "name": "Air temperature (2 m)", "short_name": "Temperature",
        "description": "Annual mean of daily mean 2 m air temperature.",
        "annual_value": "annual mean of 12 monthly means", "units": "°C", "slope_units": "°C/year",
        "dataset": {"source": "NASA POWER", "id": "POWER daily T2M (AG community)", "version": "POWER API v2 (MERRA-2 based)",
                    "provenance": "reanalysis-based model estimate", "doi": None},
        "spatial_resolution": "0.5° × 0.625° grid cell", "temporal_resolution": "daily → monthly → annual",
        "available_from": "1981-01-01", "max_years": 50, "default_period": [2015, 2025],
        "modes": {"point": True, "region": False},
        "region_unsupported_reason": "NASA POWER is served here as daily point time series for one grid cell; a region-wide statistic would require many cells and is not implemented.",
        "v1": "/api/v1/temperature/trend",
    },
    "relative_humidity": {
        "name": "Relative humidity (2 m)", "short_name": "Humidity",
        "description": "Annual mean of daily 2 m relative humidity.",
        "annual_value": "annual mean of 12 monthly means", "units": "%", "slope_units": "percentage points/year",
        "dataset": {"source": "NASA POWER", "id": "POWER daily RH2M (AG community)", "version": "POWER API v2 (MERRA-2 based)",
                    "provenance": "reanalysis-based model estimate", "doi": None},
        "spatial_resolution": "0.5° × 0.625° grid cell", "temporal_resolution": "daily → monthly → annual",
        "available_from": "1981-01-01", "max_years": 50, "default_period": [2015, 2025],
        "modes": {"point": True, "region": False},
        "region_unsupported_reason": "NASA POWER is served here as daily point time series for one grid cell; region-wide analysis is not implemented.",
        "v1": "/api/v1/relative-humidity/trend",
    },
    "extreme_heat": {
        "name": "Extreme heat frequency", "short_name": "Extreme heat",
        "description": "Share of days whose maximum temperature exceeds the local 1991–2020 calendar-day 90th percentile (bootstrap-adjusted inside the reference period).",
        "annual_value": "percentage of valid days above the local 90th-percentile threshold", "units": "% of days",
        "slope_units": "percentage points/year",
        "dataset": {"source": "NASA POWER", "id": "POWER daily T2M_MAX (AG community)", "version": "POWER API v2 (MERRA-2 based)",
                    "provenance": "reanalysis-based model estimate", "doi": None},
        "spatial_resolution": "0.5° × 0.625° grid cell", "temporal_resolution": "daily → annual exceedance frequency",
        "available_from": "1981-01-01", "max_years": 50, "default_period": [2015, 2025],
        "modes": {"point": True, "region": False},
        "region_unsupported_reason": "Thresholds are local to one NASA POWER grid cell; a regional exceedance statistic is not implemented.",
        "v1": "/api/v1/extreme-heat/trend",
    },
    "precipitation": {
        "name": "Precipitation", "short_name": "Precipitation",
        "description": "Annual total precipitation from twelve monthly accumulations.",
        "annual_value": "sum of 12 monthly accumulations", "units": "mm/year", "slope_units": "mm/year²",
        "dataset": {"source": "NASA GPM IMERG", "id": "NASA/GPM_L3/IMERG_MONTHLY_V07", "version": "V07 Final (monthly)",
                    "provenance": "satellite–gauge merged estimate", "doi": "10.5067/GPM/IMERG/3B-MONTH/07"},
        "spatial_resolution": "0.1° grid cell (≈11 km)", "temporal_resolution": "monthly → annual",
        "available_from": "2000-06-01", "max_years": 30, "default_period": [2015, 2025],
        "modes": {"point": True, "region": True},
        "region_shape": "bbox", "default_region_span_degrees": 1.0, "max_region_span_degrees": 5.0,
        "region_description": "Area-weighted mean over valid 0.1° IMERG pixels inside a latitude–longitude box; months need ≥95% valid area.",
        "region_unsupported_reason": None,
        "v1": "/api/v1/precipitation/trend", "v1_region": "/api/v1/precipitation/region/trend",
    },
    "ndvi": {
        "name": "Vegetation greenness (NDVI)", "short_name": "NDVI",
        "description": "Annual mean of quality-filtered MODIS NDVI averaged over a circular area.",
        "annual_value": "equal-weight mean of monthly means of quality-filtered 16-day composites", "units": "NDVI units",
        "slope_units": "NDVI units/year",
        "dataset": {"source": "NASA MODIS", "id": "MODIS/061/MOD13Q1", "version": "Collection 6.1",
                    "provenance": "satellite observation", "doi": "10.5067/MODIS/MOD13Q1.061"},
        "spatial_resolution": "250 m pixels averaged over a circle around the point", "temporal_resolution": "16-day → monthly → annual",
        "available_from": "2000-02-18", "max_years": 30, "default_period": [2015, 2025],
        "modes": {"point": True, "region": True},
        "region_shape": "circle", "default_radius_km": 5, "max_radius_km": 100,
        "region_unsupported_reason": None,
        "v1": "/api/v1/ndvi/trend",
    },
    "soil_moisture": {
        "name": "Soil moisture", "short_name": "Soil moisture",
        "description": "Monthly soil moisture from one dataset at a time: GLDAS-2.1 Noah 0–10 cm model layer, or SMAP L3 Enhanced (≈0–5 cm satellite retrieval), version 005 or 006.",
        "annual_value": "equal-weight mean of 12 usable monthly means", "units": "dataset-specific (kg m-2 or m3 m-3)",
        "slope_units": "dataset-specific per year",
        "dataset": {"source": "NASA GLDAS / NASA SMAP", "id": "see datasets", "version": "see datasets",
                    "provenance": "model (GLDAS) or satellite retrieval (SMAP)", "doi": None},
        "datasets": ["gldas_2_1_noah_0_10cm", "smap_l3e_v005_am", "smap_l3e_v006_am"],
        "default_dataset": "gldas_2_1_noah_0_10cm",
        "spatial_resolution": "0.25° GLDAS grid; SMAP enhanced 9 km product sampled on the EE geographic grid (not sensing resolution)", "temporal_resolution": "3-hourly or daily → monthly → annual",
        "available_from": "2000-01-01", "max_years": 27, "default_period": [2015, 2025],
        "modes": {"point": True, "region": False},
        "region_unsupported_reason": "Soil moisture uses the native grid cell containing the point; region-wide analysis is not implemented.",
        "v1": "/api/v1/soil-moisture/trend",
    },
}


# --- cache with in-flight de-duplication ---------------------------------------


class ResultCache:
    def __init__(self, max_entries: int = 128, ttl_seconds: float = 3600) -> None:
        self._max, self._ttl = max_entries, ttl_seconds
        self._data: OrderedDict[tuple, tuple[float, str, Any]] = OrderedDict()
        self._inflight: dict[tuple, asyncio.Future] = {}

    async def get_or_compute(self, key: tuple, compute):
        now = time.monotonic()
        hit = self._data.get(key)
        if hit and now - hit[0] <= self._ttl:
            self._data.move_to_end(key)
            return hit[2], {"hit": True, "retrieved_at": hit[1], "age_seconds": round(now - hit[0], 1)}
        if key in self._inflight:
            value, meta = await asyncio.shield(self._inflight[key])
            return value, {**meta, "shared_in_flight_request": True}
        future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await compute()
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            meta = {"hit": False, "retrieved_at": stamp, "age_seconds": 0.0}
            self._data[key] = (time.monotonic(), stamp, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
            future.set_result((value, meta))
            return value, meta
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved
            raise
        finally:
            del self._inflight[key]


def _cache(request: Request) -> ResultCache:
    if not hasattr(request.app.state, "unified_cache"):
        request.app.state.unified_cache = ResultCache()
    return request.app.state.unified_cache


async def _call_v1(request: Request, path: str, params: dict[str, Any]) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal", timeout=None) as client:
        response = await client.get(path, headers={"X-API-Key": request.headers.get("x-api-key", "")}, params={k: v for k, v in params.items() if v is not None})
    body = response.json()
    if response.status_code != 200:
        detail = body.get("detail", body)
        if isinstance(detail, str):
            reason = {401: "authentication_required", 422: "unsupported_request", 502: "provider_failure",
                      503: "provider_unavailable", 504: "request_timeout"}.get(response.status_code, "analysis_failed")
            detail = {"reason": reason, "message": detail}
        raise HTTPException(response.status_code, detail)
    return body


# --- normalisation ----------------------------------------------------------------


def _power_cell(lat: float, lon: float) -> dict[str, Any]:
    dlat, dlon = POWER_GRID["latitude_step"], POWER_GRID["longitude_step"]
    clat = max(-90.0, min(90.0, round(lat / dlat) * dlat))
    clon = round(lon / dlon) * dlon
    return {"center": [clat, clon], "bounds": {"south": max(-90, clat - dlat / 2), "north": min(90, clat + dlat / 2),
                                               "west": max(-180, clon - dlon / 2), "east": min(180, clon + dlon / 2)},
            "approximate": True}


def _monthly_pairs(raw) -> list[tuple[int, float]]:
    if isinstance(raw, dict):
        return sorted((int(k), float(v)) for k, v in raw.items())
    return [(int(m), float(v)) for m, v in raw or []]


def add_change_point(trend: dict[str, Any], annual: list[dict[str, Any]]) -> None:
    """Attach the sudden-step check, run on the eligible annual values."""
    values = {a["year"]: a["value"] for a in annual}
    years = [y for y in sorted(trend["eligible_years"]) if values.get(y) is not None]
    trend["change_point"] = detect_step(years, [values[y] for y in years])


def _trend(trend: dict[str, Any] | None) -> dict[str, Any] | None:
    if trend is None:
        return None
    ts, mk, sd = trend.get("theil_sen"), trend.get("mann_kendall"), trend.get("serial_dependence")
    level = trend.get("result_level")
    return {
        "result_level": level,
        "result_level_label": {
            "statistical_inference": "Slope with significance test (indicative; see caveat)",
            "descriptive_slope": "Descriptive slope only (no significance test)",
            "annual_summaries_only": "Too few eligible years for a slope",
        }.get(level, level),
        "eligible_years": trend.get("eligible_years", []),
        "excluded_years": trend.get("excluded_years", []),
        "missing_years": trend.get("missing_years", []),
        "slope": None if ts is None else ts["slope"],
        "intercept": None if ts is None else ts["intercept"],
        "slope_units": None if ts is None else ts["slope_units"],
        "confidence_interval": None if ts is None else ts.get("confidence_interval"),
        "confidence_interval_unavailable_reason": None if ts is None else ts.get("confidence_interval_unavailable_reason"),
        "mann_kendall": mk,
        "serial_dependence": sd,
        "slope_unavailable_reason": trend.get("slope_unavailable_reason"),
        "significance_unavailable_reason": trend.get("significance_unavailable_reason"),
    }


def _annual_from_shared(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in items:
        out.append({
            "year": s["year"], "value": s.get("annual_value"),
            "eligible": s["eligible_for_trend_inference"], "reasons": s.get("eligibility_reasons", []),
            "complete_calendar_year": s.get("is_complete_calendar_year"),
            "coverage_percentage": s.get("valid_coverage_percentage"),
            "represented_months": s.get("represented_months"), "missing_months": s.get("missing_months"),
            "extra": {k: s[k] for k in ("mean_spatial_coverage_percentage", "minimum_spatial_coverage_percentage",
                                        "valid_observations", "expected_observations") if k in s},
        })
    return out


def _monthly_series(items: list[dict[str, Any]], key: str = "monthly_values") -> list[dict[str, Any]]:
    series = []
    for s in items:
        for month, value in _monthly_pairs(s.get(key)):
            series.append({"date": date(s["year"], month, 1).isoformat(), "value": value})
    return series


def _seasonal_ndvi(body: dict[str, Any], slope_units: str, policy: TrendPolicy | None = None) -> dict[str, Any]:
    """NDVI trend from monthly means with the Seasonal Kendall test (see SEASONAL_TREND_METHOD).

    Cloud-masked months rarely leave complete years for the annual method (Yangon 2015-2024:
    0 of 10 years eligible), but each month can still be compared with the same month in
    other years.
    """
    monthly = {(s["year"], m): v for s in body["annual_summaries"] for m, v in _monthly_pairs(s.get("monthly_values"))}
    first = date.fromisoformat(str(body["period"]["start"])).year
    last = (date.fromisoformat(str(body["period"]["end"])) - timedelta(days=1)).year
    # Unified requests pass the configured scientific policy; direct callers retain defaults.
    result, months = seasonal_trend(monthly, first, last, slope_units.removesuffix("/year"), policy or TrendPolicy())
    trend = _trend(asdict(result))
    years = list(result.eligible_years)
    used = {k: v for k, v in monthly.items() if k[1] in months and k[0] in years}
    month_mean = {m: sum(v for (_, mm), v in used.items() if mm == m) / sum(1 for k in used if k[1] == m) for m in months}
    # Step check on each year's mean monthly anomaly, so the seasonal cycle and missing months do not fake a step.
    anomalies = [
        sum(v - month_mean[m] for (y, m), v in used.items() if y == year) / sum(1 for k in used if k[0] == year)
        for year in years
    ]
    trend.update(method="seasonal_kendall", months_used=months, sample_count=len(used),
                 change_point=detect_step(years, anomalies))
    return trend


def normalise(variable: str, body: dict[str, Any], lat: float, lon: float, mode: str = "point", policy: TrendPolicy | None = None) -> dict[str, Any]:
    meta = VARIABLES[variable]
    spatial: dict[str, Any]
    extra: dict[str, Any] = {}
    if variable in ("temperature", "relative_humidity", "extreme_heat"):
        spatial = {"mode": "point", "type": "grid_cell_estimate", "description": "NASA POWER grid-cell estimate",
                   "native_grid": body["location"].get("native_grid"), "cell": _power_cell(lat, lon)}
    elif variable == "precipitation" and body["spatial_support"]["type"] == "bbox_area_weighted_mean":
        ss = body["spatial_support"]
        b = ss["bbox"]
        accepted = sum(1 for c in body["monthly_coverage"] if c["accepted"])
        spatial = {"mode": "region", "type": "bbox_area_weighted_mean", "description": ss["description"],
                   "native_grid": "0.1°", "bbox": {"south": b["south"], "north": b["north"], "west": b["west"], "east": b["east"]},
                   "region_area_km2": body["monthly_coverage"][0]["total_area_km2"] if body["monthly_coverage"] else None,
                   "min_valid_area_fraction": ss["min_valid_area_fraction"],
                   "months_meeting_area_threshold": accepted, "single_cell_substituted": False}
    elif variable == "precipitation":
        ss = body["spatial_support"]
        c = ss["grid_cell_center"]
        h = ss["grid_spacing_degrees"] / 2
        spatial = {"mode": "point", "type": "native_grid_cell", "description": "IMERG native 0.1° grid cell containing the point",
                   "native_grid": "0.1°", "cell": {"id": ss["grid_cell_id"], "center": c,
                   "bounds": {"south": c[0] - h, "north": c[0] + h, "west": c[1] - h, "east": c[1] + h}, "approximate": False}}
    elif variable == "ndvi":
        radius = body["location"]["radius_km"]
        spatial = {"mode": mode, "type": "circle_mean", "radius_km": radius,
                   "description": (f"Mean of valid 250 m MODIS pixels within {radius:g} km of the point"
                                   + (" (small sampling area for point mode)" if mode == "point" else "")),
                   "native_grid": "250 m"}
    else:
        loc = body["location"]
        spatial = {"mode": "point", "type": "native_grid_cell", "description": "Native grid cell containing the point (no substitution)",
                   "native_grid": body["dataset"]["native_grid"], "cell": {**loc["cell"], "approximate": False},
                   "cell_status": loc["cell_status"], "coastal_proximity": loc["coastal_proximity"]}

    if variable == "extreme_heat":
        annual = [{
            "year": s["year"], "value": s.get("primary_trend_percentage"), "eligible": s["eligible_for_trend_inference"],
            "reasons": s.get("eligibility_reasons", []), "complete_calendar_year": None,
            "coverage_percentage": s.get("annual_coverage_percentage"), "represented_months": None, "missing_months": None,
            "extra": {"raw_hot_day_count": s["raw_hot_day_count"], "raw_hot_day_percentage": s["raw_hot_day_percentage"],
                      "bootstrap_adjusted_percentage": s.get("bootstrap_adjusted_percentage"),
                      "bootstrap_confidence_interval": s.get("bootstrap_confidence_interval"),
                      "valid_exposure_days": s["valid_exposure_days"]},
        } for s in body["annual_summaries"]]
        series: list[dict[str, Any]] = []
        extra = {"reference_period": body.get("reference_period"), "trend_basis": body.get("trend_basis"),
                 "threshold_method": body.get("methodology")}
    elif variable == "precipitation":
        annual = [{
            "year": s["year"], "value": s.get("annual_accumulation_mm"), "eligible": s["eligible_for_trend_inference"],
            "reasons": s.get("eligibility_reasons", []), "complete_calendar_year": s.get("is_complete_calendar_year"),
            "coverage_percentage": s.get("valid_coverage_percentage"), "represented_months": s.get("represented_months"),
            "missing_months": s.get("missing_months"),
            "extra": {"observed_accumulation_mm": s.get("observed_accumulation_mm")},
        } for s in body["annual_summaries"]]
        series = _monthly_series(body["annual_summaries"], "monthly_accumulations")
    elif variable == "soil_moisture":
        annual = _annual_from_shared(body["annual_summaries"])
        derived = {s["year"]: s.get("annual_value") for s in body.get("derived_annual_summaries") or []}
        for a in annual:
            a["extra"]["derived_volumetric"] = derived.get(a["year"])
        series = [{"date": m["month"], "value": m["mean_native"], "status": m["status"],
                   "descriptive_value": m["descriptive_mean_native"], "usable": m["usable_for_inference"]}
                  for m in body["monthly"]]
        extra = {"derived_trend": _trend(body.get("derived_trend")), "units": body["units"],
                 "diagnostics": body.get("diagnostics"), "year_support": body.get("year_support")}
    else:
        annual = _annual_from_shared(body["annual_summaries"])
        series = _monthly_series(body["annual_summaries"])

    if variable == "soil_moisture":
        d = body["dataset"]
        dataset = {"source": "NASA GLDAS" if d["provenance"] == "model" else "NASA SMAP", "id": d["collection_id"],
                   "version": d["version"], "key": d["key"], "title": d["title"], "provenance": d["product_type"],
                   "doi": d["doi"], "citation": d["citation"], "depth": d["depth"]}
        units, slope_units = body["units"]["primary"], (body["trend"]["theil_sen"] or {}).get("slope_units") or f"{body['units']['primary']}/year"
        resolution = d["native_grid"]
    else:
        dataset = dict(meta["dataset"])
        units, slope_units = meta["units"], meta["slope_units"]
        resolution = (meta["spatial_resolution"] if spatial.get("type") != "bbox_area_weighted_mean"
                      else "0.1° IMERG pixels, area-weighted over the box")

    period = body.get("period", {})
    trend = _trend(body.get("trend"))
    if variable == "ndvi":
        trend = _seasonal_ndvi(body, slope_units, policy)
    elif trend is not None:
        add_change_point(trend, annual)
    monthly_for_lab = ({(s["year"], m): v for s in body["annual_summaries"] for m, v in _monthly_pairs(s.get("monthly_values"))}
                       if variable == "ndvi" else None)
    methods_lab = build_methods_lab(variable, annual, trend, monthly_for_lab)
    return {
        "variable": {"id": variable, "name": meta["name"], "description": meta["description"],
                     "annual_value_definition": meta["annual_value"]},
        "dataset": dataset,
        "spatial_support": {**spatial, "resolution": resolution, "requested": {"latitude": lat, "longitude": lon}},
        "period": {"start": period.get("start"), "end_exclusive": period.get("end_exclusive") or period.get("end"),
                   "catalog_first_image": period.get("catalog_first_image"), "catalog_last_image": period.get("catalog_last_image")},
        "units": {"annual_value": units, "slope": slope_units},
        "annual": annual,
        "series": series,
        "series_definition": {"temperature": "monthly mean (°C)", "relative_humidity": "monthly mean (%)",
                              "precipitation": "monthly accumulation (mm/month)", "ndvi": "monthly mean NDVI",
                              "soil_moisture": f"monthly mean ({units})", "extreme_heat": None}[variable],
        "trend": trend,
        "coverage": {
            "years_requested": len(annual),
            "eligible_years": sum(1 for a in annual if a["eligible"]),
            "excluded_years": [{"year": a["year"], "reasons": a["reasons"]} for a in annual if not a["eligible"]],
        },
        "methodology": {"source": body.get("methodology"),
                        "trend_method": SEASONAL_TREND_METHOD if variable == "ndvi" else TREND_METHOD},
        "caveats": [SEASONAL_LIMITATION, SEASONAL_DESCRIPTIVE_SLOPE_NOTE] if variable == "ndvi" else [INFERENCE_CAVEAT, DESCRIPTIVE_SLOPE_NOTE],
        "limitations": body.get("limitations", []) + ([
            SEASONAL_LIMITATION,
            "The NDVI trend uses only calendar months with data in at least 70% of years: "
            + (", ".join(calendar.month_abbr[m] for m in trend["months_used"]) or "none") + ".",
        ] if variable == "ndvi" else []),
        "extra": extra,
        "methods_lab": methods_lab,
        "data_status": "live_nasa_retrieval",
    }


# --- endpoints ----------------------------------------------------------------------


@router.get("/variables")
async def variables(request: Request, verify_availability: bool = False) -> dict[str, Any]:
    settings = request.app.state.settings
    if verify_availability:
        # Explicit opt-in only; provider caches catalog results for six hours.
        await _call_v1(request, "/api/v1/soil-moisture/datasets", {"include_live_availability": "true"})
    out = []
    for key, meta in VARIABLES.items():
        item = {k: v for k, v in meta.items() if not k.startswith("v1")}
        item["id"] = key
        if key == "ndvi":
            item["max_radius_km"] = settings.ndvi_max_radius_km
            item["max_years"] = settings.ndvi_trend_max_date_range_years
        if key == "precipitation":
            item["max_years"] = settings.precipitation_max_date_range_years
        if key == "soil_moisture":
            item["max_years"] = settings.soil_moisture_max_date_range_years
        if key in ("temperature", "relative_humidity", "extreme_heat"):
            item["max_years"] = settings.power_max_date_range_years
        item["availability"] = {
            "documented_first": meta["available_from"], "documented_last": None,
            "latest_observation": None, "latest_complete_year": None,
            "verification": "documented_only", "provisional": "Recent observations may be incomplete or provisional; eligibility is evaluated after retrieval.",
        }
        item["sampling"] = {"point_radius_km": 0.25 if key == "ndvi" else None,
                            "approximate": key in ("temperature", "relative_humidity", "extreme_heat")}
        item["geographic_limitations"] = ["Coverage and quality masks can leave locations without usable observations."]
        if key == "precipitation":
            item["max_region_span_degrees"] = settings.precipitation_region_max_span_degrees
            item["min_region_span_degrees"] = 0.1
            item["region_description"] = f"Area-weighted mean over valid IMERG cells; months need at least {settings.precipitation_region_min_valid_area_fraction:.0%} valid area. Antimeridian crossing is unsupported."
        if key == "soil_moisture":
            item["products"] = []
            for d in DATASETS.values():
                product = descriptor_payload(d)
                product["availability"] = {"documented_first": d.documented_first_date.isoformat(),
                    "documented_last": d.documented_last_date.isoformat() if d.documented_last_date else None,
                    "latest_observation": None, "latest_complete_year": ((d.documented_last_date.year if d.documented_last_date.month == 12 and d.documented_last_date.day == 31 else d.documented_last_date.year - 1) if d.documented_last_date else None), "verification": "documented_only",
                    "as_of": d.availability_as_of.isoformat(), "provisional": "GLDAS provisional months are excluded from inference." if d.is_model else "Quality-filtered sampled days; missing observations remain missing."}
                # Use an already verified cached catalog result without making network calls on page load.
                service = request.app.state.soil_moisture_service
                a = service.cached_availability(d.key) if hasattr(service, "cached_availability") else None
                if a:
                    last = a.last_image_date
                    product["availability"].update(latest_observation=last.isoformat(),
                        latest_complete_year=last.year if last.month == 12 and last.day == 31 else last.year - 1,
                        verification="live_catalog_cached")
                item["products"].append(product)
            item["geographic_limitations"] = ["GLDAS: modelled land, 60°S–90°N; Greenland screening and water/ice masks apply.", "SMAP: approximately 85°S–85°N; swath and retrieval-quality masks apply."]
        out.append(item)
    return {"variables": out, "caveats": [INFERENCE_CAVEAT], "api_version": "2"}


def _year_bounds(start_date: date, end_date: date) -> None:
    if start_date >= end_date:
        raise HTTPException(422, "start_date must be before end_date")


class UnifiedAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    variable: dict[str, Any]
    dataset: dict[str, Any]
    spatial_support: dict[str, Any]
    period: dict[str, Any]
    annual: list[dict[str, Any]]
    series: list[dict[str, Any]]
    trend: dict[str, Any] | None
    investigation: dict[str, Any]
    data_status: str


@router.get("/analysis", response_model=UnifiedAnalysisResponse)
async def analysis(
    request: Request,
    variable: Literal["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"],
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date,
    mode: Literal["point", "region"] = "point",
    radius_km: Annotated[float | None, Query(gt=0)] = None,
    dataset: str | None = None,
    bbox: str | None = None,
) -> dict[str, Any]:
    meta = VARIABLES[variable]
    _year_bounds(start_date, end_date)
    if mode == "region" and not meta["modes"]["region"]:
        raise HTTPException(422, {"reason": "region_mode_unsupported", "message": meta["region_unsupported_reason"]})
    box: tuple[float, float, float, float] | None = None
    if bbox is not None:
        if meta.get("region_shape") != "bbox":
            raise HTTPException(422, {"reason": "bbox_unsupported", "message": (
                "Bounding-box regions are not supported for this variable"
                + ("; NDVI supports circular regions via radius_km." if variable == "ndvi" else ".")
            )})
        try:
            parts = tuple(float(x) for x in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(422, "bbox must be 'west,south,east,north' in degrees") from exc
        if len(parts) != 4:
            raise HTTPException(422, "bbox must be 'west,south,east,north' in degrees")
        box = (parts[0], parts[1], parts[2], parts[3])
        mode = "region"
    elif mode == "region" and meta.get("region_shape") == "bbox":
        half = meta["default_region_span_degrees"] / 2
        box = (max(-180.0, longitude - half), max(-90.0, latitude - half),
               min(180.0, longitude + half), min(90.0, latitude + half))
    params: dict[str, Any] = {"latitude": latitude, "longitude": longitude,
                              "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
    path = meta["v1"]
    if box is not None:
        params = {"west": box[0], "south": box[1], "east": box[2], "north": box[3],
                  "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        path = meta["v1_region"]
    if variable == "ndvi":
        params["radius_km"] = radius_km if radius_km is not None else (
            meta["default_radius_km"] if mode == "region" else 0.25)
    elif radius_km is not None:
        raise HTTPException(422, f"radius_km is not used for {variable}")
    if variable == "soil_moisture":
        params["dataset"] = dataset or meta["default_dataset"]
    elif dataset is not None:
        raise HTTPException(422, f"dataset selection is not available for {variable}")

    key = (variable, mode, round(latitude, 4), round(longitude, 4), start_date, end_date,
           params.get("radius_km"), params.get("dataset"), box)

    async def compute():
        body = await _call_v1(request, path, params)
        settings = request.app.state.settings
        policy = TrendPolicy(settings.trend_min_slope_years, settings.trend_min_significance_years,
                             settings.trend_significance_alpha, settings.trend_min_adjacent_pairs,
                             settings.trend_material_lag1_rho)
        return normalise(variable, body, latitude, longitude, mode, policy)

    payload, cache_meta = await _cache(request).get_or_compute(key, compute)
    identity = {"variable": variable, "dataset": payload["dataset"]["id"], "version": payload["dataset"]["version"],
                "latitude": round(latitude, 4), "longitude": round(longitude, 4), "mode": mode,
                "radius_km": params.get("radius_km"), "bbox": box,
                "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
    request_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return {**payload, "investigation": {"id": request_id, "request": identity,
            "requested_period": {"start": start_date.isoformat(), "end_exclusive": end_date.isoformat()},
            "effective_years": (payload.get("trend") or {}).get("eligible_years", []),
            "source": payload["dataset"]["source"], "method": "seasonal_sen" if variable == "ndvi" else "theil_sen",
            "retrieved_at": cache_meta["retrieved_at"],
            "provenance_status": "cached_nasa_retrieval" if cache_meta["hit"] else payload["data_status"]}, "cache": cache_meta,
            "data_status": "cached_nasa_retrieval" if cache_meta["hit"] else payload["data_status"]}


@router.get("/relationships")
async def relationships(
    request: Request,
    variables: str,
    latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date,
    soil_moisture_dataset: str | None = None,
    radius_km: Annotated[float | None, Query(gt=0)] = None,
) -> dict[str, Any]:
    names = [v.strip() for v in variables.split(",") if v.strip()]
    if len(names) != 2 or len(set(names)) != 2 or any(n not in VARIABLES for n in names):
        raise HTTPException(422, "variables must name exactly two different variables")
    results = []
    for name in names:
        results.append(await analysis(
            request, name, latitude, longitude, start_date, end_date, "point",
            radius_km if name == "ndvi" else None,
            soil_moisture_dataset if name == "soil_moisture" else None, None))
    eligible = [{a["year"]: a["value"] for a in r["annual"] if a["eligible"] and a["value"] is not None} for r in results]
    common = sorted(set(eligible[0]) & set(eligible[1]))
    x = [eligible[0][y] for y in common]
    y = [eligible[1][y] for y in common]
    rho = rho_diff = None
    reasons = []
    if len(common) >= 8:
        r1 = spearmanr(x, y).statistic
        rho = None if r1 != r1 else float(r1)
        consecutive = [(i, i + 1) for i in range(len(common) - 1) if common[i + 1] - common[i] == 1]
        if len(consecutive) >= 7:
            dx = [x[j] - x[i] for i, j in consecutive]
            dy = [y[j] - y[i] for i, j in consecutive]
            r2 = spearmanr(dx, dy).statistic
            rho_diff = None if r2 != r2 else float(r2)
        else:
            reasons.append("too_few_consecutive_years_for_first_difference_correlation")
    else:
        reasons.append("fewer_than_8_common_eligible_years")
    supports = [r["spatial_support"] for r in results]
    return {
        "variables": names,
        "results": {name: r for name, r in zip(names, results)},
        "alignment": {
            "temporal": "calendar-year annual values; only years eligible for both variables are used",
            "spatial": [f"{r['variable']['name']}: {s['description']} ({s['resolution']})" for r, s in zip(results, supports)],
            "spatial_supports_differ": len({s["resolution"] for s in supports}) > 1,
        },
        "common_eligible_years": common,
        "paired_values": [{"year": yr, names[0]: a, names[1]: b} for yr, a, b in zip(common, x, y)],
        "spearman_rho_annual": rho,
        "spearman_rho_first_differences": rho_diff,
        "unavailable_reasons": reasons,
        "interpretation": (
            "Descriptive association only. Correlation of annual values does not show that one variable "
            "causes the other; shared trends, seasonality, and different spatial footprints can produce "
            "correlation. The first-difference correlation removes much of the shared trend. No p-values are reported."
        ),
    }


_GEOCODE_CACHE: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
_GEOCODE_INFLIGHT: dict[str, "asyncio.Future[list[dict[str, Any]]]"] = {}
_GEOCODE_TTL_SECONDS = 86400
# Nominatim usage policy: at most 1 request/second, identifying User-Agent, cache results.
# https://operations.osmfoundation.org/policies/nominatim/ (one process; see outbound_throttle.py)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "EarthSystemTrendDetective/0.3 (+https://github.com/josephliu-4545/code-me-to-the-moon---ETSD)"
_NOMINATIM_THROTTLE = OutboundThrottle(min_interval_seconds=1.0, max_wait_seconds=5.0)


async def _nominatim_search(q: str) -> list[dict[str, Any]]:
    try:
        await _NOMINATIM_THROTTLE.acquire()
    except ThrottleBusy as exc:
        raise HTTPException(503, "place search is busy; try again in a few seconds, or enter coordinates") from exc
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": NOMINATIM_USER_AGENT}) as client:
            r = await client.get(NOMINATIM_URL, params={"q": q, "format": "jsonv2", "limit": 6})
        r.raise_for_status()
        raw = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "place search is unavailable; enter coordinates or click the map") from exc
    results = []
    for item in raw if isinstance(raw, list) else []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon):
            results.append({"name": item.get("display_name", ""), "latitude": lat, "longitude": lon,
                            "type": item.get("type")})
    return results


@router.get("/geocode")
async def geocode(q: Annotated[str, Query(min_length=2, max_length=120)]) -> dict[str, Any]:
    key = " ".join(q.strip().lower().split())
    hit = _GEOCODE_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _GEOCODE_TTL_SECONDS:
        return {"query": q, "results": hit[1], "source": "OpenStreetMap Nominatim (cached)",
                "attribution": "© OpenStreetMap contributors"}
    pending = _GEOCODE_INFLIGHT.get(key)
    if pending is not None:  # an identical search is already running: share its result
        results = await asyncio.shield(pending)
    else:
        future: asyncio.Future[list[dict[str, Any]]] = asyncio.get_running_loop().create_future()
        _GEOCODE_INFLIGHT[key] = future
        try:
            results = await _nominatim_search(q)
            future.set_result(results)
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved when nobody else is waiting
            raise
        finally:
            _GEOCODE_INFLIGHT.pop(key, None)
        _GEOCODE_CACHE[key] = (time.monotonic(), results)
        while len(_GEOCODE_CACHE) > 256:
            _GEOCODE_CACHE.popitem(last=False)
    return {"query": q, "results": results, "source": "OpenStreetMap Nominatim",
            "attribution": "© OpenStreetMap contributors"}
