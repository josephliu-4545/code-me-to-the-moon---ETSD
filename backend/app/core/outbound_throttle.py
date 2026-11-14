"""Process-wide spacing of outbound requests to a rate-limited public service.

Used for OpenStreetMap Nominatim, whose public usage policy allows at most one request per
second (https://operations.osmfoundation.org/policies/nominatim/). Each caller reserves the
next free start slot under a lock, then waits outside the lock, so concurrent requests can
never start closer together than `min_interval_seconds`, and nobody waits longer than
`max_wait_seconds` (they get ThrottleBusy instead of queueing without bound).

This coordinates one backend process only. A deployment with several instances needs a
shared limiter or a geocoding service whose terms allow that traffic.
"""

import asyncio
import time
from threading import Lock
from typing import Awaitable, Callable


class ThrottleBusy(RuntimeError):
    """The next free slot is further away than the caller is allowed to wait."""


class OutboundThrottle:
    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        max_wait_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.max_wait_seconds = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._next_free = float("-inf")
        self._lock = Lock()  # no await inside the critical section, so a thread lock is safe here

    def reserve(self) -> float:
        """Reserve the next start slot; returns the delay before the caller may start."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_free)
            delay = slot - now
            if delay > self.max_wait_seconds:
                raise ThrottleBusy(f"next slot in {delay:.1f} s")
            self._next_free = slot + self.min_interval_seconds
            return delay

    async def acquire(self) -> None:
        delay = self.reserve()
        if delay > 0:
            await self._sleep(delay)
