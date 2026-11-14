"""Server-side Earth Engine authentication for a shared backend.

Local development keeps using each developer's own `earthengine authenticate`
credentials. A shared deployment instead points EE_SERVICE_ACCOUNT_KEY_FILE at a
service-account JSON key stored outside the repository (for example a mounted
secret). The key is read only when Earth Engine is first initialised, is never
logged or returned by the API, and never reaches the frontend.
"""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import ee


class ServiceAccountConfigError(ValueError):
    """The configured service-account key is missing or malformed (message has no secrets)."""


def read_service_account_email(key_file: str) -> str:
    path = Path(key_file)
    if not path.is_file():
        raise ServiceAccountConfigError("EE_SERVICE_ACCOUNT_KEY_FILE does not point to a readable file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ServiceAccountConfigError("EE_SERVICE_ACCOUNT_KEY_FILE is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise ServiceAccountConfigError("EE_SERVICE_ACCOUNT_KEY_FILE is not a service-account key")
    email = data.get("client_email")
    if not isinstance(email, str) or "@" not in email or not data.get("private_key"):
        raise ServiceAccountConfigError("the service-account key is missing client_email or private_key")
    return email


def key_file_inside(key_file: str, directory: Path) -> bool:
    try:
        Path(key_file).resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


class ServiceAccountEarthEngine:
    """Drop-in for the `ee` module whose Initialize uses service-account credentials."""

    def __init__(self, key_file: str, ee_module: ModuleType | Any = ee) -> None:
        self._key_file = key_file
        self._ee = ee_module

    def Initialize(self, *, project: str) -> None:  # noqa: N802 (mirrors ee.Initialize)
        email = read_service_account_email(self._key_file)
        credentials = self._ee.ServiceAccountCredentials(email, key_file=self._key_file)
        self._ee.Initialize(credentials=credentials, project=project)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ee, name)


def earth_engine_module(key_file: str | None) -> ModuleType | ServiceAccountEarthEngine:
    return ServiceAccountEarthEngine(key_file) if key_file else ee


def auth_mode(key_file: str | None) -> str:
    return "service_account" if key_file else "local_user_credentials"
