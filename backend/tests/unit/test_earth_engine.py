from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.earth_engine import (
    EarthEngineConfigurationError,
    EarthEngineInitializationError,
    EarthEngineManager,
    EarthEngineStatus,
)


class FakeEarthEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.projects: list[str] = []

    def Initialize(self, *, project: str) -> None:
        self.projects.append(project)
        if self.error:
            raise self.error


def test_initialize_requires_project_id() -> None:
    manager = EarthEngineManager(None, FakeEarthEngine())

    with pytest.raises(EarthEngineConfigurationError):
        manager.initialize()

    assert manager.status is EarthEngineStatus.FAILED


def test_initialize_runs_only_once() -> None:
    fake_ee = FakeEarthEngine()
    manager = EarthEngineManager("project-id", fake_ee)

    manager.initialize()
    manager.initialize()

    assert fake_ee.projects == ["project-id"]
    assert manager.status is EarthEngineStatus.READY


def test_concurrent_initialize_runs_only_once() -> None:
    fake_ee = FakeEarthEngine()
    manager = EarthEngineManager("project-id", fake_ee)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: manager.initialize(), range(8)))

    assert fake_ee.projects == ["project-id"]


def test_initialization_failure_is_cached_and_sanitized() -> None:
    fake_ee = FakeEarthEngine(RuntimeError("secret credential path"))
    manager = EarthEngineManager("project-id", fake_ee)

    with pytest.raises(EarthEngineInitializationError, match="initialization failed") as first:
        manager.initialize()
    with pytest.raises(EarthEngineInitializationError) as second:
        manager.initialize()

    assert "secret" not in str(first.value)
    assert "secret" not in str(second.value)
    assert fake_ee.projects == ["project-id"]
    assert manager.status is EarthEngineStatus.FAILED



def test_failure_is_retried_after_the_pause_but_not_before() -> None:
    now = [0.0]
    fake_ee = FakeEarthEngine(RuntimeError("network down"))
    manager = EarthEngineManager("project-id", fake_ee, retry_after_seconds=60, clock=lambda: now[0])

    with pytest.raises(EarthEngineInitializationError):
        manager.initialize()
    now[0] = 30
    with pytest.raises(EarthEngineInitializationError):
        manager.initialize()  # still cached
    assert fake_ee.projects == ["project-id"]

    fake_ee.error = None
    now[0] = 61
    manager.initialize()  # retried and recovered
    assert fake_ee.projects == ["project-id", "project-id"]
    assert manager.status is EarthEngineStatus.READY


def test_missing_project_is_never_retried() -> None:
    now = [0.0]
    manager = EarthEngineManager(None, FakeEarthEngine(), retry_after_seconds=1, clock=lambda: now[0])
    with pytest.raises(EarthEngineConfigurationError):
        manager.initialize()
    now[0] = 100
    with pytest.raises(EarthEngineConfigurationError):
        manager.initialize()


def test_initialize_bounds_network_reads_and_restores_the_default() -> None:
    import socket

    seen: list[float | None] = []

    class RecordingEarthEngine:
        def Initialize(self, *, project: str) -> None:
            seen.append(socket.getdefaulttimeout())

    assert socket.getdefaulttimeout() is None
    EarthEngineManager("project-id", RecordingEarthEngine(), network_timeout_seconds=12).initialize()
    assert seen == [12]
    assert socket.getdefaulttimeout() is None


def test_hung_start_up_fails_after_the_timeout_instead_of_blocking() -> None:
    import threading
    import time

    release = threading.Event()

    class HangingEarthEngine:
        def Initialize(self, *, project: str) -> None:
            release.wait(5)

    manager = EarthEngineManager("project-id", HangingEarthEngine(), startup_timeout_seconds=0.2)
    started = time.monotonic()
    with pytest.raises(EarthEngineInitializationError):
        manager.initialize()
    release.set()
    assert time.monotonic() - started < 2
    assert manager.status is EarthEngineStatus.FAILED


def test_start_up_sets_a_deadline_on_later_requests() -> None:
    deadlines: list[int] = []

    class Data:
        def setDeadline(self, milliseconds: int) -> None:
            deadlines.append(milliseconds)

    class EarthEngineWithData(FakeEarthEngine):
        data = Data()

    EarthEngineManager("project-id", EarthEngineWithData(), request_deadline_seconds=12).initialize()
    assert deadlines == [12000]
