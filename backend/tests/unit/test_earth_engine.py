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

