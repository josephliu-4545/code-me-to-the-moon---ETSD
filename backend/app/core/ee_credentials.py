"""Server-side Earth Engine authentication for a shared backend.

Three mutually exclusive modes:

* local_user_credentials (default): the developer's own `earthengine authenticate`
  credentials. If none exist, the Earth Engine library itself falls back to Google
  Application Default Credentials.
* application_default_credentials (EE_USE_APPLICATION_DEFAULT_CREDENTIALS=true): keyless.
  Credentials come from Google Application Default Credentials only, for example the
  service account attached to a Cloud Run service through the metadata server. No key
  file exists anywhere. Recommended for Cloud Run.
* service_account (EE_SERVICE_ACCOUNT_KEY_FILE): a service-account JSON key stored outside
  the repository (for example a mounted secret). Use only where keyless identity is unavailable.

Configuring both a key file and ADC is rejected rather than guessed. Credentials are read only
when Earth Engine is first initialised, are never logged or returned by the API, and never
reach the frontend.
"""

import json
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import ee
import google.auth

# Scopes requested for keyless credentials (Earth Engine accepts either; cloud-platform covers the project).
EE_SCOPES = ("https://www.googleapis.com/auth/earthengine", "https://www.googleapis.com/auth/cloud-platform")
CONFLICT_MESSAGE = (
    "Configure either EE_SERVICE_ACCOUNT_KEY_FILE or EE_USE_APPLICATION_DEFAULT_CREDENTIALS, not both"
)


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


class ApplicationDefaultEarthEngine:
    """Drop-in for the `ee` module that authenticates with Application Default Credentials only."""

    def __init__(self, ee_module: ModuleType | Any = ee,
                 default_credentials: Callable[..., tuple[Any, Any]] | None = None) -> None:
        self._ee = ee_module
        self._default = default_credentials or google.auth.default

    def Initialize(self, *, project: str) -> None:  # noqa: N802 (mirrors ee.Initialize)
        credentials, _ = self._default(scopes=list(EE_SCOPES))
        self._ee.Initialize(credentials=credentials, project=project)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ee, name)


class ConflictingEarthEngineConfig:
    """Fails initialisation safely when two credential sources are configured."""

    def __init__(self, ee_module: ModuleType | Any = ee) -> None:
        self._ee = ee_module

    def Initialize(self, *, project: str) -> None:  # noqa: N802
        raise ServiceAccountConfigError(CONFLICT_MESSAGE)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ee, name)


def earth_engine_module(key_file: str | None, use_application_default: bool = False) -> Any:
    if key_file and use_application_default:
        return ConflictingEarthEngineConfig()
    if use_application_default:
        return ApplicationDefaultEarthEngine()
    return ServiceAccountEarthEngine(key_file) if key_file else ee


def auth_mode(key_file: str | None, use_application_default: bool = False) -> str:
    if key_file and use_application_default:
        return "conflicting_configuration"
    if use_application_default:
        return "application_default_credentials"
    return "service_account" if key_file else "local_user_credentials"
