import asyncio
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
from typing import TypeVar


ResultT = TypeVar("ResultT")


class OperationBusyError(RuntimeError):
    pass


class OperationTimeoutError(RuntimeError):
    pass


class BoundedOperationRunner:
    def __init__(
        self,
        max_concurrent: int,
        operation_name: str = "Earth Engine",
        thread_name_prefix: str = "earth-engine",
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be positive")
        self._capacity = BoundedSemaphore(max_concurrent)
        self._operation_name = operation_name
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix=thread_name_prefix,
        )
        self._active = 0
        self._active_lock = Lock()
        self._idle = Event()
        self._idle.set()

    async def run(
        self,
        operation: Callable[[], ResultT],
        timeout_seconds: float,
    ) -> ResultT:
        if not self._capacity.acquire(blocking=False):
            raise OperationBusyError(f"{self._operation_name} operation capacity is exhausted")

        self._mark_started()
        try:
            future = self._executor.submit(operation)
        except BaseException:
            self._mark_finished()
            raise

        future.add_done_callback(self._release_capacity)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while not future.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise OperationTimeoutError(
                    f"{self._operation_name} operation timed out"
                )
            await asyncio.sleep(min(0.01, remaining))
        return future.result()

    def _mark_started(self) -> None:
        with self._active_lock:
            self._active += 1
            self._idle.clear()

    def _release_capacity(self, _future: Future[object]) -> None:
        self._mark_finished()

    def _mark_finished(self) -> None:
        self._capacity.release()
        with self._active_lock:
            self._active -= 1
            if self._active == 0:
                self._idle.set()

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

