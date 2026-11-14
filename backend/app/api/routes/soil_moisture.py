from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.scientific_notes import TREND_METHOD
from app.core.config import Settings
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import BoundedOperationRunner, OperationBusyError, OperationTimeoutError
from app.services.soil_moisture_provider import SoilMoistureRetrievalError, UnsupportedLocationError
from app.services.soil_moisture_service import SoilMoistureComparison, SoilMoistureResult, SoilMoistureService
from app.soil_moisture.aggregation import annual_policy
from app.soil_moisture.datasets import DATASETS, UnknownDatasetError, get_dataset


router = APIRouter(prefix="/api/v1", tags=["soil-moisture"])


def get_soil_moisture_service(request: Request) -> SoilMoistureService:
    return request.app.state.soil_moisture_service


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _runner(request: Request) -> BoundedOperationRunner:
    return request.app.state.operation_runner


def descriptor_payload(d) -> dict[str, Any]:
    return {
        "key": d.key, "title": d.title, "variable": d.variable,
        "product_type": d.product_type, "provenance": "model" if d.is_model else "satellite",
        "quantity_kind": d.quantity_kind, "native_units": d.native_units,
        "derived_units": "m3 m-3" if d.supports_derived_volumetric else None,
        "depth": {"top_cm": d.depth_top_cm, "bottom_cm": d.depth_bottom_cm, "semantics": d.depth_semantics},
        "collection_id": d.collection_ids[0], "version": d.version, "band": d.band, "qc_band": d.qc_band,
        "native_grid": d.native_grid, "nominal_scale_m": d.nominal_scale_m,
        "temporal_sampling": d.temporal_sampling,
        "documented_availability": {"first": d.documented_first_date, "last": d.documented_last_date,
                                    "as_of": d.availability_as_of},
        "doi": d.doi, "citation": d.citation, "is_primary": d.is_primary,
        "limitations": list(d.limitations),
    }


def _validate(dataset: str | None, start_date: date, end_date: date, settings: Settings) -> None:
    if dataset is not None:
        try:
            get_dataset(dataset)
        except UnknownDatasetError as exc:
            raise HTTPException(422, str(exc)) from exc
    if start_date.day != 1 or end_date.day != 1:
        raise HTTPException(422, "start_date and end_date must be the first day of a month (end is exclusive)")
    if start_date >= end_date:
        raise HTTPException(422, "start_date must be before end_date")
    years = (end_date.year - start_date.year) + (end_date.month - start_date.month) / 12
    if years > settings.soil_moisture_max_date_range_years:
        raise HTTPException(422, f"date range exceeds {settings.soil_moisture_max_date_range_years} years")


async def _run(runner: BoundedOperationRunner, settings: Settings, operation):
    try:
        return await runner.run(operation, timeout_seconds=settings.soil_moisture_request_timeout_seconds)
    except UnsupportedLocationError as exc:
        raise HTTPException(422, {"reason": exc.reason, "message": str(exc)}) from exc
    except OperationBusyError as exc:
        raise HTTPException(503, "Earth Engine is busy; retry later") from exc
    except OperationTimeoutError as exc:
        raise HTTPException(504, "Earth Engine request timed out") from exc
    except EarthEngineError as exc:
        raise HTTPException(503, "Earth Engine is unavailable") from exc
    except SoilMoistureRetrievalError as exc:
        raise HTTPException(502, "Earth Engine soil moisture retrieval failed") from exc


def _month_payload(r) -> dict[str, Any]:
    out = asdict(r)
    out["slot_coverage"] = r.slot_coverage
    out["usable_for_inference"] = r.usable_for_inference
    out["inference_exclusion_reasons"] = list(r.inference_exclusion_reasons)
    return out


def serialize_result(result: SoilMoistureResult, service: SoilMoistureService, include_trend: bool) -> dict[str, Any]:
    a, p, d = result.analysis, result.provider, result.descriptor
    cell = p.cell
    policy = service.support_policy
    payload: dict[str, Any] = {
        "variable": "soil_moisture",
        "dataset": descriptor_payload(d),
        "location": {
            "latitude": result.latitude, "longitude": result.longitude,
            "support_type": "native_grid_cell",
            "cell": {"id": cell.cell_id, "center": [cell.center_latitude, cell.center_longitude],
                     "bounds": {"south": cell.south, "north": cell.north, "west": cell.west, "east": cell.east},
                     "size_degrees": cell.cell_size_degrees, "crs": cell.crs},
            "cell_status": result.cell_status,
            "valid_cells_in_3x3": p.valid_cells_in_3x3,
            "coastal_proximity": result.coastal_proximity,
            "substituted_cell": False,
        },
        "period": {"start": result.start, "end_exclusive": result.end,
                   "catalog_first_image": p.availability.first_image_date,
                   "catalog_last_image": p.availability.last_image_date},
        "units": {"primary": a.units, "derived": a.derived_units,
                  "derivation": "theta = S / (1000 kg m-3 x 0.10 m)" if a.derived_units else None,
                  "derived_is_layer_mean_not_equivalent_to_smap": bool(a.derived_units)},
        "monthly": [_month_payload(r) for r in a.monthly.months],
        "year_support": [asdict(y) for y in a.year_support],
        "annual_summaries": [asdict(s) for s in a.annual_summaries],
        "derived_annual_summaries": None if a.derived_annual_summaries is None else [asdict(s) for s in a.derived_annual_summaries],
        "diagnostics": {**p.diagnostics, "frozen_layer_possible_months": [m.isoformat() for m in p.frozen_months]},
        "methodology": {
            "value_definition": a.value_definition,
            "annual_aggregation": a.annual_aggregation,
            "monthly_support_policy": {**asdict(policy), "status": policy.status},
            "annual_policy": asdict(annual_policy(d)),
            "trend_policy": asdict(service.trend_policy),
            "thresholds_are_universal_standards": False,
            "missing_values": "retained as missing; never zero, interpolated, or filled from another dataset or version",
            "provisional_months": "months with any non-permanent catalog image (or, if status is unknown, within the configured window before the latest image) are shown but excluded from trends",
            "trend_method": TREND_METHOD,
        },
        "limitations": list(result.limitations),
    }
    if include_trend:
        payload["trend"] = asdict(a.trend)
        payload["derived_trend"] = None if a.derived_trend is None else asdict(a.derived_trend)
        payload["slope_per_decade"] = (a.trend.theil_sen.slope * 10) if a.trend.theil_sen else None
    return payload


@router.get("/soil-moisture/datasets")
async def soil_moisture_datasets(
    include_live_availability: bool = False,
    service: SoilMoistureService = Depends(get_soil_moisture_service),
    settings: Settings = Depends(_settings), runner: BoundedOperationRunner = Depends(_runner),
):
    items = [descriptor_payload(d) for d in DATASETS.values()]
    if include_live_availability:
        def load():
            return {k: service.availability(k) for k in DATASETS}
        live = await _run(runner, settings, load)
        for item in items:
            a = live[item["key"]]
            item["live_availability"] = {"first_image": a.first_image_date, "last_image": a.last_image_date}
    return {"variable": "soil_moisture", "datasets": items,
            "datasets_are_merged": False,
            "note": "Each dataset is analysed independently; SMAP versions 005 and 006 are separate datasets."}


@router.get("/soil-moisture")
async def soil_moisture(
    dataset: str, latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date, radius_km: float | None = None,
    service: SoilMoistureService = Depends(get_soil_moisture_service),
    settings: Settings = Depends(_settings), runner: BoundedOperationRunner = Depends(_runner),
):
    if radius_km is not None:
        raise HTTPException(422, "soil moisture uses the native grid cell; radius_km is not supported")
    _validate(dataset, start_date, end_date, settings)
    result = await _run(runner, settings, lambda: service.analyze(dataset, latitude, longitude, start_date, end_date))
    return serialize_result(result, service, include_trend=False)


@router.get("/soil-moisture/trend")
async def soil_moisture_trend(
    dataset: str, latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date, radius_km: float | None = None,
    service: SoilMoistureService = Depends(get_soil_moisture_service),
    settings: Settings = Depends(_settings), runner: BoundedOperationRunner = Depends(_runner),
):
    if radius_km is not None:
        raise HTTPException(422, "soil moisture uses the native grid cell; radius_km is not supported")
    _validate(dataset, start_date, end_date, settings)
    result = await _run(runner, settings, lambda: service.analyze(dataset, latitude, longitude, start_date, end_date))
    return serialize_result(result, service, include_trend=True)


def serialize_comparison(c: SoilMoistureComparison, service: SoilMoistureService) -> dict[str, Any]:
    return {
        "variable": "soil_moisture",
        "datasets_are_merged": False,
        "results": {r.descriptor.key: serialize_result(r, service, include_trend=True) for r in c.results},
        "common_eligible_years": list(c.common_eligible_years),
        "differences": list(c.differences),
        "descriptive_agreement": {
            "slope_sign_agreement": c.slope_sign_agreement,
            "pairs": [
                {"datasets": list(p.datasets), "common_valid_months": p.common_valid_months,
                 "mean_difference_m3_m3": p.mean_difference_m3_m3,
                 "mean_difference_label": "systematic difference (first minus second), not error; neither dataset is ground truth",
                 "monthly_anomaly_spearman_rho": p.monthly_anomaly_spearman_rho,
                 "unavailable_reasons": list(p.unavailable_reasons)}
                for p in c.pairs
            ],
            "excluded_frozen_months": c.excluded_frozen_months,
            "inferential_test_of_slope_difference": None,
        },
        "interpretation": "Descriptive comparison only. Agreement does not validate either dataset, and correlation is not causation.",
    }


@router.get("/soil-moisture/compare")
async def soil_moisture_compare(
    datasets: str, latitude: Annotated[float, Query(ge=-90, le=90)], longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date, end_date: date,
    service: SoilMoistureService = Depends(get_soil_moisture_service),
    settings: Settings = Depends(_settings), runner: BoundedOperationRunner = Depends(_runner),
):
    keys = tuple(k.strip() for k in datasets.split(",") if k.strip())
    if not 2 <= len(keys) <= 3 or len(set(keys)) != len(keys):
        raise HTTPException(422, "datasets must list 2 or 3 distinct dataset keys")
    for k in keys:
        _validate(k, start_date, end_date, settings)
    comparison = await _run(runner, settings, lambda: service.compare(keys, latitude, longitude, start_date, end_date))
    return serialize_comparison(comparison, service)
