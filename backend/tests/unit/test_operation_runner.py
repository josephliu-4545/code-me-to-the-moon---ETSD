from threading import Event

import pytest

from app.core.operation_runner import (
    BoundedOperationRunner,
    OperationBusyError,
    OperationTimeoutError,
)


@pytest.mark.anyio
async def test_runner_returns_worker_result() -> None:
    runner = BoundedOperationRunner(max_concurrent=1)
    try:
        assert await runner.run(lambda: 42, timeout_seconds=1) == 42
    finally:
        runner.shutdown()


@pytest.mark.anyio
async def test_runner_propagates_worker_error() -> None:
    runner = BoundedOperationRunner(max_concurrent=1)

    def fail() -> None:
        raise ValueError("broken")

    try:
        with pytest.raises(ValueError, match="broken"):
            await runner.run(fail, timeout_seconds=1)
    finally:
        runner.shutdown()


@pytest.mark.anyio
async def test_timeout_retains_capacity_until_worker_finishes() -> None:
    started = Event()
    release = Event()
    runner = BoundedOperationRunner(max_concurrent=1)

    def blocked() -> str:
        started.set()
        release.wait(timeout=2)
        return "done"

    try:
        with pytest.raises(OperationTimeoutError):
            await runner.run(blocked, timeout_seconds=0.01)
        assert started.wait(timeout=1)

        with pytest.raises(OperationBusyError):
            await runner.run(lambda: "new", timeout_seconds=1)

        release.set()
        assert runner.wait_for_idle(timeout=1)
        assert await runner.run(lambda: "new", timeout_seconds=1) == "new"
    finally:
        release.set()
        runner.shutdown()



@pytest.mark.anyio
async def test_queued_request_waits_for_a_freed_slot() -> None:
    import asyncio

    release = Event()
    runner = BoundedOperationRunner(max_concurrent=1, queue_timeout_seconds=2)
    try:
        first = asyncio.ensure_future(runner.run(lambda: release.wait(timeout=2) and "first", timeout_seconds=3))
        await asyncio.sleep(0.05)
        second = asyncio.ensure_future(runner.run(lambda: "second", timeout_seconds=3))
        await asyncio.sleep(0.2)
        assert not second.done()  # waiting in the queue, not rejected
        release.set()
        assert await first == "first"
        assert await second == "second"
    finally:
        release.set()
        runner.shutdown()


@pytest.mark.anyio
async def test_queued_request_gives_up_after_queue_timeout() -> None:
    import asyncio
    import time

    release = Event()
    runner = BoundedOperationRunner(max_concurrent=1, queue_timeout_seconds=0.3)
    try:
        first = asyncio.ensure_future(runner.run(lambda: release.wait(timeout=2), timeout_seconds=3))
        await asyncio.sleep(0.05)
        started = time.monotonic()
        with pytest.raises(OperationBusyError):
            await runner.run(lambda: "late", timeout_seconds=3)
        assert 0.25 <= time.monotonic() - started < 1.5
        release.set()
        await first
    finally:
        release.set()
        runner.shutdown()


def test_negative_queue_timeout_is_rejected() -> None:
    with pytest.raises(ValueError):
        BoundedOperationRunner(max_concurrent=1, queue_timeout_seconds=-1)
