"""Multi-dataset catalog and comparison endpoints (/api/v2/datasets, /api/v2/compare).

Each selected dataset is analysed independently (primary datasets through the existing
validated pipelines, alternatives through the generic monthly Earth Engine pipeline).
A failure in one dataset is reported for that dataset only; the others still return.
"""

import asyncio
from dataclasses import asdict, fields
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.routes import unified
from app.api.scientific_notes import DESCRIPTIVE_SLOPE_NOTE, INFERENCE_CAVEAT, TREND_METHOD
from app.comparison import engine
from app.comparison.catalog import CATALOG, NOT_YET_COMPARABLE, DatasetEntry, entries, find, relationship
from app.comparison.providers import ComparisonRetrievalError, EEMonthlyProvider, analyze_months, normalise_monthly
from app.core.earth_engine import EarthEngineError
from app.core.operation_runner import OperationBusyError, OperationTimeoutError
from app.services.soil_moisture_provider import UnsupportedLocationError


router = APIRouter(prefix="/api/v2", tags=["comparison"])

_INTERNAL = {"backend", "v1_variable", "v1_dataset", "method", "band", "crs_transform", "scale", "offset",
             "valid_range", "status_property", "min_month_coverage", "extra", "annual_rule"}

OUTCOME_LABELS = {
    "inference": "Trend with significance test (indicative)",
    "descriptive_only": "Descriptive trend only; significance not supported",
    "insufficient_coverage": "Data found, but too few complete years for a trend",
    "no_data": "No valid data for this location and period",
    "unsupported_location": "Dataset does not cover this location",
    "unsupported_mode": "Dataset does not support this analysis mode",
    "outside_record": "Requested period is outside this dataset's record or request limit",
    "provider_error": "The data provider failed or timed out",
}


def entry_payload(e: DatasetEntry) -> dict[str, Any]:
    out = {f.name: getattr(e, f.name) for f in fields(e) if f.name not in _INTERNAL}
    out["supports_region"] = "region" in e.modes
    return out


def _provider(request: Request) -> EEMonthlyProvider:
    state = request.app.state
    if not hasattr(state, "comparison_provider"):
        state.comparison_provider = EEMonthlyProvider(state.ee_manager)
    return state.comparison_provider


def _uses_earth_engine(e: DatasetEntry) -> bool:
    return e.backend == "ee_monthly" or e.v1_variable in {"precipitation", "ndvi", "soil_moisture"}


def _outcome(analysis: dict[str, Any]) -> str:
    if not any(a["value"] is not None for a in analysis["annual"]):
        return "no_data"
    trend = analysis.get("trend") or {}
    if trend.get("slope") is None:
        return "insufficient_coverage"
    return "inference" if trend.get("result_level") == "statistical_inference" else "descriptive_only"


async def _analyse(request: Request, e: DatasetEntry, lat: float, lon: float, start: date, end: date,
                   mode: str, radius_km: float | None, bbox: str | None) -> dict[str, Any]:
    if mode == "region" and "region" not in e.modes:
        raise _Outcome("unsupported_mode", f"{e.name} supports point analysis only; no regional statistic is computed.")
    first = date.fromisoformat(e.available_from)
    last = date.fromisoformat(e.available_to) if e.available_to else None
    if end <= first or (last and start > last):
        raise _Outcome("outside_record", f"{e.name} covers {e.available_from} to {e.available_to or 'present'}.")
    if (end.year - start.year) > e.max_years:
        raise _Outcome("outside_record", f"{e.name} allows at most {e.max_years} years per request.")
    if e.backend == "v1":
        return await unified.analysis(
            request, variable=e.v1_variable, latitude=lat, longitude=lon, start_date=start, end_date=end,
            mode=mode, radius_km=radius_km, dataset=e.v1_dataset, bbox=bbox)
    settings = request.app.state.settings
    provider = _provider(request)

    def run():
        result = provider.fetch(e, lat, lon, start, end)
        summaries, trend = analyze_months(e, list(result.months))
        payload = normalise_monthly(e, result, summaries, trend, lat, lon, start, end, unified._trend,
                                    [INFERENCE_CAVEAT, DESCRIPTIVE_SLOPE_NOTE], TREND_METHOD)
        if payload["trend"] is not None:
            unified.add_change_point(payload["trend"], payload["annual"])
        return payload

    return await request.app.state.operation_runner.run(run, timeout_seconds=settings.soil_moisture_request_timeout_seconds)


class _Outcome(Exception):
    def __init__(self, outcome: str, message: str) -> None:
        super().__init__(message)
        self.outcome = outcome


async def _safe(request, e, lat, lon, start, end, mode, radius_km, bbox, lock: asyncio.Lock | None) -> dict[str, Any]:
    entry = entry_payload(e)
    try:
        if lock is not None:
            async with lock:
                analysis = await _analyse(request, e, lat, lon, start, end, mode, radius_km, bbox)
        else:
            analysis = await _analyse(request, e, lat, lon, start, end, mode, radius_km, bbox)
    except _Outcome as exc:
        return {"entry": entry, "outcome": exc.outcome, "message": str(exc), "analysis": None}
    except UnsupportedLocationError as exc:
        return {"entry": entry, "outcome": "unsupported_location", "message": str(exc), "analysis": None}
    except HTTPException as exc:
        detail = exc.detail
        reason = detail.get("reason") if isinstance(detail, dict) else None
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
        if exc.status_code == 422 and reason in {"outside_dataset_coverage", "unsupported_land_cover_region"}:
            outcome = "unsupported_location"
        elif exc.status_code == 422:
            outcome = "outside_record"
        else:
            outcome = "provider_error"
        return {"entry": entry, "outcome": outcome, "message": message, "http_status": exc.status_code, "analysis": None}
    except (OperationBusyError, OperationTimeoutError, EarthEngineError, ComparisonRetrievalError) as exc:
        return {"entry": entry, "outcome": "provider_error", "message": str(exc) or type(exc).__name__, "analysis": None}
    outcome = _outcome(analysis)
    return {"entry": entry, "outcome": outcome, "message": OUTCOME_LABELS[outcome], "analysis": analysis}


@router.get("/datasets", summary="Datasets available per variable", description="Catalog of datasets per environmental variable with provenance, units, resolution, record, quality control, lineage and pairwise comparability. Variables without alternatives explain why.")
async def datasets(variable: str | None = None) -> dict[str, Any]:
    variables = [variable] if variable else list(CATALOG) + list(NOT_YET_COMPARABLE)
    out = []
    for v in variables:
        items = entries(v)
        if not items and v not in NOT_YET_COMPARABLE:
            raise HTTPException(422, f"unknown variable {v!r}")
        out.append({
            "variable": v,
            "datasets": [entry_payload(e) for e in items],
            "comparison_available": len(items) >= 2,
            "not_yet_available_reason": NOT_YET_COMPARABLE.get(v),
            "relationships": [
                {"datasets": [a.key, b.key], "lineage": relationship(a, b)[0], "note": relationship(a, b)[1],
                 "numerically_comparable": a.comparable_quantity == b.comparable_quantity}
                for i, a in enumerate(items) for b in items[i + 1:]
            ],
        })
    return {"variables": out, "outcomes": OUTCOME_LABELS}


@router.get("/compare", summary="Compare datasets for one variable", description="Analyses 2-4 datasets of one variable independently at the same location and period, then compares them descriptively. Invalid requests return 422; a dataset that fails (unsupported location, outside record, provider error, no data) is reported in results[key].outcome while the others still return (HTTP 200). Datasets are never merged.")
async def compare(
    request: Request,
    variable: str,
    datasets: str,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    start_date: date,
    end_date: date,
    mode: str = "point",
    radius_km: Annotated[float | None, Query(gt=0)] = None,
    bbox: str | None = None,
) -> dict[str, Any]:
    if variable not in CATALOG:
        raise HTTPException(422, {"reason": "comparison_unavailable",
                                  "message": NOT_YET_COMPARABLE.get(variable, f"unknown variable {variable!r}")})
    keys = [k.strip() for k in datasets.split(",") if k.strip()]
    if not 2 <= len(keys) <= 4 or len(set(keys)) != len(keys):
        raise HTTPException(422, "datasets must list 2 to 4 distinct dataset keys")
    selected = []
    for k in keys:
        e = find(variable, k)
        if e is None:
            raise HTTPException(422, f"dataset {k!r} is not in the {variable} catalog")
        selected.append(e)
    if mode not in {"point", "region"}:
        raise HTTPException(422, "mode must be 'point' or 'region'")
    if start_date >= end_date or start_date.day != 1 or end_date.day != 1:
        raise HTTPException(422, "start_date must precede end_date and both must be the first day of a month")

    ee_lock = asyncio.Lock()   # Earth Engine datasets run one at a time to respect the shared EE quota
    tasks = [_safe(request, e, latitude, longitude, start_date, end_date, mode, radius_km, bbox,
                   ee_lock if _uses_earth_engine(e) else None) for e in selected]
    results = await asyncio.gather(*tasks)
    succeeded = [(e, r["analysis"]) for e, r in zip(selected, results) if r["analysis"] is not None]
    return {
        "variable": variable,
        "location": {"latitude": latitude, "longitude": longitude, "mode": mode},
        "period": {"start": start_date.isoformat(), "end_exclusive": end_date.isoformat()},
        "datasets_requested": keys,
        "datasets_are_merged": False,
        "results": {e.key: r for e, r in zip(selected, results)},
        "succeeded": [e.key for e, _ in succeeded],
        "comparison": engine.compare(succeeded) if len(succeeded) >= 2 else None,
        "comparison_unavailable_reason": None if len(succeeded) >= 2 else "fewer than two datasets returned results",
        "caveats": [
            "Each dataset is analysed independently with its own quality rules; datasets are never merged, averaged or gap-filled.",
            "Agreement does not prove accuracy, and no dataset is treated as ground truth.",
            INFERENCE_CAVEAT,
        ],
    }
