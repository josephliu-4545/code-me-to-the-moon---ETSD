from enum import StrEnum
from threading import Lock
from types import ModuleType
from typing import Protocol

import ee


class EarthEngineModule(Protocol):
    def Initialize(self, *, project: str) -> None: ...


class EarthEngineStatus(StrEnum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    FAILED = "failed"


class EarthEngineError(RuntimeError):
    """Base class for sanitized Earth Engine lifecycle errors."""


class EarthEngineConfigurationError(EarthEngineError):
    pass


class EarthEngineInitializationError(EarthEngineError):
    pass


class EarthEngineManager:
    def __init__(
        self,
        project_id: str | None,
        ee_module: EarthEngineModule | ModuleType = ee,
    ) -> None:
        self._project_id = project_id
        self.ee = ee_module
        self._status = EarthEngineStatus.UNINITIALIZED
        self._error: EarthEngineError | None = None
        self._lock = Lock()

    @property
    def status(self) -> EarthEngineStatus:
        return self._status

    def initialize(self) -> None:
        if self._status is EarthEngineStatus.READY:
            return

        with self._lock:
            if self._status is EarthEngineStatus.READY:
                return
            if self._status is EarthEngineStatus.FAILED:
                assert self._error is not None
                raise self._error

            if not self._project_id:
                self._error = EarthEngineConfigurationError(
                    "Earth Engine project is not configured"
                )
                self._status = EarthEngineStatus.FAILED
                raise self._error

            try:
                self.ee.Initialize(project=self._project_id)
            except Exception as exc:
                self._error = EarthEngineInitializationError(
                    "Earth Engine initialization failed"
                )
                self._status = EarthEngineStatus.FAILED
                raise self._error from exc

            self._status = EarthEngineStatus.READY

