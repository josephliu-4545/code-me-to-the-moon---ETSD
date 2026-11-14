"""Configuration status for teammates and operators. Never returns secrets."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from app.core.access import parse_keys
from app.core.access import ProxyTrust
from app.core.ee_credentials import (
    CONFLICT_MESSAGE,
    ServiceAccountConfigError,
    auth_mode,
    key_file_inside,
    read_service_account_email,
)


router = APIRouter(prefix="/api/v2", tags=["status"])

REPO_ROOT = Path(__file__).resolve().parents[4]

AUTH_DESCRIPTIONS = {
    "local_user_credentials": "Developer credentials from `earthengine authenticate`; the Earth Engine library falls back to Application Default Credentials if none exist.",
    "application_default_credentials": "Keyless: Google Application Default Credentials, such as the service account attached to the hosting service. No key file.",
    "service_account": "Service-account key file mounted from outside the repository.",
    "conflicting_configuration": "Both a key file and Application Default Credentials are configured; Earth Engine will not start until one is removed.",
}


@router.get("/status", summary="Backend configuration status",
            description="Reports whether Earth Engine is configured, how it authenticates, and whether access keys and rate limits are enabled. Contains no credentials.")
async def status(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    key_file = settings.ee_service_account_key_file
    use_adc = settings.ee_use_application_default_credentials
    mode = auth_mode(key_file, use_adc)
    warnings: list[str] = []
    service_account_ok: bool | None = None
    if not settings.ee_project_id:
        warnings.append("EE_PROJECT_ID is not set: NDVI, precipitation and soil moisture are unavailable; NASA POWER variables still work.")
    if mode == "conflicting_configuration":
        warnings.append(CONFLICT_MESSAGE + ".")
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
    initialization = getattr(manager, "status", "unknown")
    initialization = str(getattr(initialization, "value", initialization))
    proxy_trust: ProxyTrust = getattr(request.app.state, "proxy_trust", ProxyTrust())
    if proxy_trust.ignored_reason:
        warnings.append(proxy_trust.ignored_reason)
    return {
        "api_version": "2",
        "earth_engine": {
            "project_configured": bool(settings.ee_project_id),
            "auth_mode": mode,
            "auth_description": AUTH_DESCRIPTIONS[mode],
            "service_account_key_valid": service_account_ok,
            "initialization": initialization,
            # True only after this process has initialised Earth Engine with these credentials.
            "credentials_verified": initialization == "ready",
            "max_concurrent_operations": settings.ee_max_concurrent_operations,
        },
        "access": {
            "api_key_required": bool(parse_keys(settings.api_keys)),
            "rate_limit_per_minute": settings.rate_limit_per_minute or None,
        },
        "client_identification": proxy_trust.describe(),
        "warnings": warnings,
    }
