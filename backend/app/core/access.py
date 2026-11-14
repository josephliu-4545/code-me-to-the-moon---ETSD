"""Optional API access control and per-client rate limiting for a shared backend.

Both are off by default, so local development is unchanged:
* API_KEYS (comma-separated) enables an `X-API-Key` header requirement for /api/*.
* RATE_LIMIT_PER_MINUTE (> 0) enables a token bucket per client (API key, else IP).
  Earth Engine-heavy endpoints cost more tokens. Exceeding it returns 429 + Retry-After.

Keys are compared in constant time and never echoed. Clients are identified by a
short hash, so keys never appear in logs or memory structures as plain text.

Client addresses for IP-based limits come from the direct TCP peer. Forwarding headers
(X-Forwarded-For) are client-controlled and are used only when TRUST_PROXY_HEADERS is on
AND the direct peer is a configured trusted proxy (TRUSTED_PROXY_IPS). The client address is
then read TRUSTED_PROXY_HOPS entries from the right of the header, i.e. the address written by
the outermost trusted proxy; anything a client prepends is ignored. Malformed or too-short
headers fall back to the direct peer, never to the unverified text.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import ipaddress
import math
import re
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


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class ProxyTrust:
    """Which direct peers may set X-Forwarded-For, and how many trusted proxies append to it."""

    enabled: bool = False
    networks: tuple[Network, ...] = ()
    any_peer: bool = False
    hops: int = 1
    # Why forwarding headers are ignored despite TRUST_PROXY_HEADERS (a misconfiguration), if so.
    ignored_reason: str | None = None

    def describe(self) -> dict[str, object]:
        """Status summary without addresses (no infrastructure details are published)."""
        if not self.enabled:
            mode = "direct_peer_only"
        elif self.any_peer:
            mode = "platform_proxy_any_peer"
        else:
            mode = "trusted_proxy_list"
        return {"mode": mode, "trusted_proxy_hops": self.hops if self.enabled else None,
                "trusted_proxy_count": len(self.networks) if self.enabled and not self.any_peer else None}


def parse_proxy_trust(trust_headers: bool, trusted_ips: str | None, hops: int = 1) -> ProxyTrust:
    """Build the trust boundary. Any misconfiguration fails safe: headers are ignored."""
    if not trust_headers:
        return ProxyTrust()
    if hops < 1:
        return ProxyTrust(ignored_reason="TRUSTED_PROXY_HOPS must be at least 1; forwarding headers are ignored.")
    entries = [e.strip() for e in (trusted_ips or "").split(",") if e.strip()]
    if not entries:
        return ProxyTrust(ignored_reason=(
            "TRUST_PROXY_HEADERS is on but TRUSTED_PROXY_IPS is empty; forwarding headers are ignored "
            "and clients are identified by their direct connection address."))
    if entries == ["*"]:
        return ProxyTrust(enabled=True, any_peer=True, hops=hops)
    networks: list[Network] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            return ProxyTrust(ignored_reason="TRUSTED_PROXY_IPS contains an invalid address or network; forwarding headers are ignored.")
    return ProxyTrust(enabled=True, networks=tuple(networks), hops=hops)


_IPV4_WITH_PORT = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):\d{1,5}$")
_IPV6_BRACKETED = re.compile(r"^\[([0-9A-Fa-f:.]+)\](?::\d{1,5})?$")


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    text = value.strip().strip('"')
    match = _IPV4_WITH_PORT.match(text) or _IPV6_BRACKETED.match(text)
    if match:
        text = match.group(1)
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    # Report IPv4-mapped IPv6 peers as plain IPv4 so one client has one identity.
    return address.ipv4_mapped or address if isinstance(address, ipaddress.IPv6Address) else address


def client_address(peer: str | None, forwarded_for: list[str], trust: ProxyTrust) -> str:
    """Address used to identify a client for rate limiting (see module docstring)."""
    peer_ip = _parse_ip(peer)
    direct = str(peer_ip) if peer_ip else "unknown"
    if not trust.enabled or not forwarded_for:
        return direct
    if not trust.any_peer and (peer_ip is None or not any(peer_ip in net for net in trust.networks)):
        return direct  # not from a trusted proxy: the header is client-controlled
    entries = [e.strip() for header in forwarded_for for e in header.split(",")]
    if len(entries) < trust.hops:
        return direct
    candidate = _parse_ip(entries[len(entries) - trust.hops])
    return str(candidate) if candidate else direct


def cost_for(path: str) -> int:
    return next((c for prefix, c in HEAVY_PREFIXES.items() if path.startswith(prefix)), 1)


class AccessControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_keys: tuple[str, ...], bucket: TokenBucket | None, proxy_trust: ProxyTrust | None = None) -> None:
        super().__init__(app)
        self._keys = api_keys
        self._bucket = bucket
        self._proxy_trust = proxy_trust or ProxyTrust()

    def _client_ip(self, request: Request) -> str:
        peer = request.client.host if request.client else None
        return client_address(peer, request.headers.getlist("x-forwarded-for"), self._proxy_trust)

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
