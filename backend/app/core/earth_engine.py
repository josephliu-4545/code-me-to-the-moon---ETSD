from enum import StrEnum
import socket
from threading import Event, Lock, Thread
import time
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
        network_timeout_seconds: float = 30.0,
        retry_after_seconds: float = 60.0,
        startup_timeout_seconds: float = 45.0,
        request_deadline_seconds: float = 180.0,
        clock=time.monotonic,
    ) -> None:
        self._project_id = project_id
        self.ee = ee_module
        self._status = EarthEngineStatus.UNINITIALIZED
        self._error: EarthEngineError | None = None
        self._lock = Lock()
        self._network_timeout_seconds = network_timeout_seconds
        self._retry_after_seconds = retry_after_seconds
        self._startup_timeout_seconds = startup_timeout_seconds
        self._request_deadline_seconds = request_deadline_seconds
        self._clock = clock
        self._failed_at = 0.0
        self._initialization_thread: Thread | None = None
        self._initialization_done: Event | None = None
        self._initialization_errors: list[BaseException] = []

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
                # A missing project never fixes itself; a network failure may, so retry after a pause.
                if (isinstance(self._error, EarthEngineConfigurationError)
                        or self._clock() - self._failed_at < self._retry_after_seconds):
                    raise self._error

            if not self._project_id:
                self._error = EarthEngineConfigurationError(
                    "Earth Engine project is not configured"
                )
                self._status = EarthEngineStatus.FAILED
                raise self._error

            # ee.Initialize downloads a dataset catalog with urllib and no timeout; a stalled read
            # used to hang every Earth Engine request until restart. A default socket timeout bounds
            # it (the library treats that download as optional). Applied only during start-up.
            previous_timeout = socket.getdefaulttimeout()
            if previous_timeout is None:
                socket.setdefaulttimeout(self._network_timeout_seconds)
            try:
                self._initialize_with_timeout()
            except Exception as exc:
                self._error = EarthEngineInitializationError(
                    "Earth Engine initialization failed"
                )
                self._status = EarthEngineStatus.FAILED
                self._failed_at = self._clock()
                raise self._error from exc
            finally:
                if previous_timeout is None:
                    socket.setdefaulttimeout(None)

            # Bound every later Earth Engine HTTP call too, so a stalled call frees its slot.
            data = getattr(self.ee, "data", None)  # test doubles have no ee.data
            if data is not None:
                data.setDeadline(int(self._request_deadline_seconds * 1000))
            self._status = EarthEngineStatus.READY

    def _initialize_with_timeout(self) -> None:
        # ee.Initialize also fetches its API description through requests with no timeout; behind
        # a proxy that TLS handshake was seen to hang forever. Run it in a daemon thread and give
        # up after a deadline: start-up then fails and is retried later instead of blocking all requests.
        if self._initialization_thread is None:
            self._initialization_done = Event()
            self._initialization_errors = []

            def run() -> None:
                try:
                    self.ee.Initialize(project=self._project_id)
                except BaseException as exc:  # re-raised in the caller's thread
                    self._initialization_errors.append(exc)
                finally:
                    assert self._initialization_done is not None
                    self._initialization_done.set()

            self._initialization_thread = Thread(target=run, name="earth-engine-startup", daemon=True)
            self._initialization_thread.start()

        assert self._initialization_done is not None
        if not self._initialization_done.wait(self._startup_timeout_seconds):
            raise TimeoutError(f"Earth Engine start-up took longer than {self._startup_timeout_seconds:g} s")
        errors = self._initialization_errors
        self._initialization_thread = None
        self._initialization_done = None
        self._initialization_errors = []
        if errors:
            raise errors[0]

