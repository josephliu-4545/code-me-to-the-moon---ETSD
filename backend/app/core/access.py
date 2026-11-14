"""Optional API access control and per-client rate limiting for a shared backend.

Both are off by default, so local development is unchanged:
* API_KEYS (comma-separated) enables an `X-API-Key` header requirement for /api/*.
* RATE_LIMIT_PER_MINUTE (> 0) enables a token bucket per client (API key, else IP).
  Earth Engine-heavy endpoints cost more tokens. Exceeding it returns 429 + Retry-After.

Keys are compared in constant time and never echoed. Clients are identified by a
short hash, so keys never appear in logs or memory structures as plain text.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import math
import time
from threading import Lock
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


OPEN_PATHS = ("/api/v2/status",)
HEAVY_PREFIXES = {"/api/v2/compare": 3, "/api/v1/soil-moisture/compare": 3}


def parse_keys(raw: str | None) -> tuple[str, ...]:
    return tuple(k.strip() for k in (raw or "").split(",") if k.strip())


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass
class TokenBucket:
    per_minute: int
    clock: Callable[[], float] = time.monotonic
    _state: dict[str, tuple[float, float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def take(self, client: str, cost: int = 1) -> float:
        """Spend `cost` tokens; returns 0 when allowed, else seconds until enough tokens exist."""
        capacity = float(self.per_minute)
        rate = capacity / 60.0
        cost = min(cost, self.per_minute)  # a heavy request must always be possible at full capacity
        now = self.clock()
        with self._lock:
            tokens, last = self._state.get(client, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens >= cost:
                self._state[client] = (tokens - cost, now)
                return 0.0
            self._state[client] = (tokens, now)
            if len(self._state) > 10_000:  # bound memory under many distinct clients
                for key in list(self._state)[:5_000]:
                    del self._state[key]
            return (cost - tokens) / rate


def cost_for(path: str) -> int:
    return next((c for prefix, c in HEAVY_PREFIXES.items() if path.startswith(prefix)), 1)


class AccessControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_keys: tuple[str, ...], bucket: TokenBucket | None, trust_proxy_headers: bool = False) -> None:
        super().__init__(app)
        self._keys = api_keys
        self._bucket = bucket
        self._trust_proxy = trust_proxy_headers

    def _client_ip(self, request: Request) -> str:
        if self._trust_proxy:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or path in OPEN_PATHS:
            return await call_next(request)
        supplied = request.headers.get("x-api-key", "")
        if self._keys:
            if not supplied or not any(hmac.compare_digest(supplied, k) for k in self._keys):
                return JSONResponse(status_code=401, content={"detail": {
                    "reason": "api_key_required",
                    "message": "This shared backend requires a team access key (X-API-Key header). Ask the project maintainer for one.",
                }})
        if self._bucket is not None:
            client = f"key:{fingerprint(supplied)}" if (self._keys and supplied) else f"ip:{self._client_ip(request)}"
            wait = self._bucket.take(client, cost_for(path))
            if wait > 0:
                retry = max(1, math.ceil(wait))
                return JSONResponse(status_code=429, headers={"Retry-After": str(retry)}, content={"detail": {
                    "reason": "rate_limited",
                    "message": f"Too many requests from this client; retry in about {retry} s. Earth Engine capacity is shared by the whole team.",
                }})
        return await call_next(request)
