"""Configuration status for teammates and operators. Never returns secrets."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from app.core.access import parse_keys
from app.core.ee_credentials import ServiceAccountConfigError, auth_mode, key_file_inside, read_service_account_email


router = APIRouter(prefix="/api/v2", tags=["status"])

REPO_ROOT = Path(__file__).resolve().parents[4]


@router.get("/status", summary="Backend configuration status",
            description="Reports whether Earth Engine is configured, how it authenticates, and whether access keys and rate limits are enabled. Contains no credentials.")
async def status(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    key_file = settings.ee_service_account_key_file
    warnings: list[str] = []
    service_account_ok: bool | None = None
    if not settings.ee_project_id:
        warnings.append("EE_PROJECT_ID is not set: NDVI, precipitation and soil moisture are unavailable; NASA POWER variables still work.")
    if key_file:
        try:
            read_service_account_email(key_file)
            service_account_ok = True
        except ServiceAccountConfigError as exc:
            service_account_ok = False
            warnings.append(str(exc))
        if key_file_inside(key_file, REPO_ROOT):
            warnings.append("The service-account key file is inside the repository folder; move it outside so it can never be committed.")
    manager = request.app.state.ee_manager
    return {
        "api_version": "2",
        "earth_engine": {
            "project_configured": bool(settings.ee_project_id),
            "auth_mode": auth_mode(key_file),
            "service_account_key_valid": service_account_ok,
            "initialization": str(getattr(manager, "status", "unknown")),
            "max_concurrent_operations": settings.ee_max_concurrent_operations,
        },
        "access": {
            "api_key_required": bool(parse_keys(settings.api_keys)),
            "rate_limit_per_minute": settings.rate_limit_per_minute or None,
        },
        "warnings": warnings,
    }
