"""Production foundation: client identification behind proxies, Nominatim throttling,
Earth Engine authentication selection, production settings and single-origin serving."""

import asyncio
import json
from pathlib import Path
import re

import httpx
from fastapi.testclient import TestClient
import pytest

from app.api.routes import unified
from app.core.access import ProxyTrust, client_address, parse_proxy_trust
from app.core.config import Settings
from app.core.earth_engine import EarthEngineInitializationError, EarthEngineManager
from app.core.ee_credentials import (
    CONFLICT_MESSAGE,
    EE_SCOPES,
    ApplicationDefaultEarthEngine,
    ConflictingEarthEngineConfig,
    ServiceAccountEarthEngine,
    auth_mode,
    earth_engine_module,
)
from app.core.outbound_throttle import OutboundThrottle, ThrottleBusy
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[2]
REAL_ASYNC_CLIENT = httpx.AsyncClient  # tests patch httpx.AsyncClient for outbound calls


def app_client(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, ee_project_id="test", **settings)))


# --- client identification behind proxies ------------------------------------------------

TRUSTED = parse_proxy_trust(True, "10.0.0.0/8, 192.168.1.5", hops=1)


def test_forwarding_headers_are_ignored_by_default() -> None:
    off = parse_proxy_trust(False, "10.0.0.0/8", hops=1)
    assert off.enabled is False and off.ignored_reason is None
    assert client_address("198.51.100.7", ["203.0.113.1"], off) == "198.51.100.7"


def test_spoofed_header_from_untrusted_peer_is_ignored() -> None:
    assert client_address("198.51.100.7", ["1.2.3.4"], TRUSTED) == "198.51.100.7"


def test_trusted_proxy_uses_the_entry_it_wrote_not_client_prefixes() -> None:
    # The client prepended "1.2.3.4"; the trusted proxy appended the real client address.
    assert client_address("10.1.2.3", ["1.2.3.4, 203.0.113.9"], TRUSTED) == "203.0.113.9"
    assert client_address("192.168.1.5", ["203.0.113.9"], TRUSTED) == "203.0.113.9"


def test_multiple_trusted_hops_and_multiple_header_lines() -> None:
    two = parse_proxy_trust(True, "10.0.0.0/8", hops=2)
    # client-spoof, real client (written by outer proxy), outer proxy (written by inner proxy)
    assert client_address("10.0.0.2", ["6.6.6.6, 203.0.113.9", "10.0.0.1"], two) == "203.0.113.9"


@pytest.mark.parametrize("header", ["", "   ", "not-an-ip", "203.0.113.9, garbage", "999.1.1.1", ",,"])
def test_malformed_forwarded_values_fall_back_to_the_direct_peer(header) -> None:
    assert client_address("10.1.2.3", [header], TRUSTED) == "10.1.2.3"


def test_header_shorter_than_the_trusted_chain_falls_back_to_peer() -> None:
    two = parse_proxy_trust(True, "10.0.0.0/8", hops=2)
    assert client_address("10.0.0.2", ["203.0.113.9"], two) == "10.0.0.2"


def test_ports_ipv6_and_mapped_addresses_are_normalised() -> None:
    assert client_address("10.1.2.3", ["203.0.113.9:4711"], TRUSTED) == "203.0.113.9"
    assert client_address("10.1.2.3", ["[2001:db8::1]:443"], TRUSTED) == "2001:db8::1"
    assert client_address("::ffff:198.51.100.7", [], TRUSTED) == "198.51.100.7"
    assert client_address(None, ["203.0.113.9"], TRUSTED) == "unknown"


def test_misconfiguration_fails_safe_and_is_explained() -> None:
    empty = parse_proxy_trust(True, "", hops=1)
    assert empty.enabled is False and "TRUSTED_PROXY_IPS is empty" in empty.ignored_reason
    bad = parse_proxy_trust(True, "10.0.0.0/8, nonsense", hops=1)
    assert bad.enabled is False and "invalid" in bad.ignored_reason
    zero = parse_proxy_trust(True, "10.0.0.1", hops=0)
    assert zero.enabled is False and "at least 1" in zero.ignored_reason
    for trust in (empty, bad, zero):
        assert client_address("198.51.100.7", ["203.0.113.9"], trust) == "198.51.100.7"


def test_platform_mode_trusts_any_peer_only_when_explicitly_configured() -> None:
    platform = parse_proxy_trust(True, "*", hops=1)
    assert platform.any_peer and client_address("169.254.1.1", ["6.6.6.6, 203.0.113.9"], platform) == "203.0.113.9"


def test_rotating_spoofed_headers_cannot_bypass_the_rate_limit() -> None:
    c = app_client(rate_limit_per_minute=3)  # TRUST_PROXY_HEADERS stays off
    codes = [c.get("/api/v2/variables", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_trust_without_a_proxy_list_still_cannot_be_bypassed() -> None:
    c = app_client(rate_limit_per_minute=2, trust_proxy_headers=True)
    codes = [c.get("/api/v2/variables", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_api_key_identity_is_unchanged_by_proxy_settings() -> None:
    c = app_client(api_keys="k1,k2", rate_limit_per_minute=1, trust_proxy_headers=True, trusted_proxy_ips="*")
    assert c.get("/api/v2/variables", headers={"X-API-Key": "k1", "X-Forwarded-For": "203.0.113.1"}).status_code == 200
    assert c.get("/api/v2/variables", headers={"X-API-Key": "k1", "X-Forwarded-For": "203.0.113.2"}).status_code == 429
    assert c.get("/api/v2/variables", headers={"X-API-Key": "k2"}).status_code == 200


def test_status_reports_proxy_mode_without_addresses() -> None:
    body = app_client(trust_proxy_headers=True, trusted_proxy_ips="10.9.8.0/24").get("/api/v2/status").json()
    assert body["client_identification"] == {"mode": "trusted_proxy_list", "trusted_proxy_hops": 1, "trusted_proxy_count": 1}
    assert "10.9.8" not in json.dumps(body)
    default = app_client().get("/api/v2/status").json()
    assert default["client_identification"]["mode"] == "direct_peer_only"
    misconfigured = app_client(trust_proxy_headers=True).get("/api/v2/status").json()
    assert any("TRUSTED_PROXY_IPS is empty" in w for w in misconfigured["warnings"])


# --- Nominatim throttling ------------------------------------------------------------------


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_reservations_are_spaced_and_bounded() -> None:
    t = FakeTime()
    throttle = OutboundThrottle(1.0, max_wait_seconds=1.5, clock=t.clock, sleep=t.sleep)
    assert [throttle.reserve(), throttle.reserve()] == [0.0, 1.0]
    with pytest.raises(ThrottleBusy):
        throttle.reserve()  # would have to wait 2 s
    t.now += 5
    assert throttle.reserve() == 0.0


@pytest.mark.anyio
async def test_concurrent_acquires_start_at_least_one_second_apart() -> None:
    t = FakeTime()
    throttle = OutboundThrottle(1.0, max_wait_seconds=10, clock=t.clock, sleep=t.sleep)
    starts: list[float] = []

    async def worker() -> None:
        delay = throttle.reserve()
        starts.append(t.now + delay)

    await asyncio.gather(*(worker() for _ in range(5)))
    starts.sort()
    assert all(b - a >= 1.0 for a, b in zip(starts, starts[1:]))


class RecordingNominatim:
    """Stands in for httpx.AsyncClient; records calls and can be slowed down or made to fail."""

    calls: list[dict] = []
    started_at: list[float] = []
    clock = staticmethod(lambda: 0.0)
    headers: list[dict] = []
    status = 200
    gate: asyncio.Event | None = None

    def __init__(self, *a, headers=None, **k) -> None:
        RecordingNominatim.headers.append(headers or {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        RecordingNominatim.calls.append(params)
        RecordingNominatim.started_at.append(RecordingNominatim.clock())
        if RecordingNominatim.gate is not None:
            await RecordingNominatim.gate.wait()
        body = [{"display_name": params["q"], "lat": "16.8", "lon": "96.1", "type": "city"}]
        return httpx.Response(RecordingNominatim.status, json=body, request=httpx.Request("GET", url))


@pytest.fixture
def nominatim(monkeypatch):
    unified._GEOCODE_CACHE.clear()
    unified._GEOCODE_INFLIGHT.clear()
    RecordingNominatim.calls, RecordingNominatim.headers, RecordingNominatim.status, RecordingNominatim.gate = [], [], 200, None
    t = FakeTime()
    RecordingNominatim.started_at, RecordingNominatim.clock = [], staticmethod(t.clock)
    monkeypatch.setattr(unified, "_NOMINATIM_THROTTLE", OutboundThrottle(1.0, max_wait_seconds=5, clock=t.clock, sleep=t.sleep))
    monkeypatch.setattr(unified.httpx, "AsyncClient", RecordingNominatim)
    return t


async def _get(app, path):
    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


@pytest.mark.anyio
async def test_identical_concurrent_searches_make_one_outbound_request(nominatim) -> None:
    app = create_app(Settings(_env_file=None, ee_project_id="test"))
    RecordingNominatim.gate = asyncio.Event()
    tasks = [asyncio.create_task(_get(app, "/api/v2/geocode?q=Yangon")) for _ in range(4)]
    await asyncio.sleep(0.05)
    RecordingNominatim.gate.set()
    responses = await asyncio.gather(*tasks)
    assert [r.status_code for r in responses] == [200] * 4
    assert len(RecordingNominatim.calls) == 1
    assert unified._GEOCODE_INFLIGHT == {}


@pytest.mark.anyio
async def test_distinct_searches_are_spaced_by_the_global_throttle(nominatim) -> None:
    app = create_app(Settings(_env_file=None, ee_project_id="test"))
    responses = await asyncio.gather(*(_get(app, f"/api/v2/geocode?q=place{i}") for i in range(3)))
    assert all(r.status_code == 200 for r in responses)
    assert len(RecordingNominatim.calls) == 3
    starts = sorted(RecordingNominatim.started_at)
    assert all(b - a >= 1.0 for a, b in zip(starts, starts[1:])), starts
    assert len(nominatim.slept) == 2  # the second and third request waited for their slots


def test_cache_prevents_repeat_requests_and_normalises_queries(nominatim) -> None:
    c = app_client()
    assert c.get("/api/v2/geocode", params={"q": "Yangon  Myanmar"}).status_code == 200
    second = c.get("/api/v2/geocode", params={"q": " yangon myanmar "}).json()
    assert len(RecordingNominatim.calls) == 1 and "cached" in second["source"]


def test_identifying_user_agent_is_sent(nominatim) -> None:
    app_client().get("/api/v2/geocode", params={"q": "Nairobi"})
    ua = RecordingNominatim.headers[-1]["User-Agent"]
    assert ua.startswith("EarthSystemTrendDetective/") and "github.com" in ua


def test_provider_errors_are_502_and_not_cached(nominatim) -> None:
    RecordingNominatim.status = 503
    c = app_client()
    assert c.get("/api/v2/geocode", params={"q": "Atlantis"}).status_code == 502
    RecordingNominatim.status = 200
    assert c.get("/api/v2/geocode", params={"q": "Atlantis"}).status_code == 200
    assert len(RecordingNominatim.calls) == 2


def test_overloaded_throttle_returns_503_instead_of_queueing(nominatim, monkeypatch) -> None:
    busy = OutboundThrottle(1.0, max_wait_seconds=0.5, clock=nominatim.clock, sleep=nominatim.sleep)
    busy.reserve()  # slot taken; the next request would wait 1 s > 0.5 s
    monkeypatch.setattr(unified, "_NOMINATIM_THROTTLE", busy)
    r = app_client().get("/api/v2/geocode", params={"q": "Lima"})
    assert r.status_code == 503 and "busy" in r.json()["detail"]
    assert RecordingNominatim.calls == []


# --- Earth Engine authentication selection ------------------------------------------------


class FakeEE:
    def __init__(self) -> None:
        self.calls: list = []

    def Initialize(self, credentials=None, project=None):  # noqa: N802
        self.calls.append((credentials, project))


def test_auth_modes_are_selected_explicitly() -> None:
    import ee
    assert auth_mode(None, False) == "local_user_credentials" and earth_engine_module(None, False) is ee
    assert auth_mode(None, True) == "application_default_credentials"
    assert isinstance(earth_engine_module(None, True), ApplicationDefaultEarthEngine)
    assert auth_mode("k.json", False) == "service_account" and isinstance(earth_engine_module("k.json", False), ServiceAccountEarthEngine)
    assert auth_mode("k.json", True) == "conflicting_configuration"
    assert isinstance(earth_engine_module("k.json", True), ConflictingEarthEngineConfig)


def test_application_default_credentials_are_keyless_and_scoped() -> None:
    fake, seen = FakeEE(), {}

    def default(scopes=None):
        seen["scopes"] = scopes
        return "adc-credentials", "some-project"

    ApplicationDefaultEarthEngine(fake, default).Initialize(project="demo-project")
    assert fake.calls == [("adc-credentials", "demo-project")]
    assert seen["scopes"] == list(EE_SCOPES)


def test_missing_application_default_credentials_fail_safely() -> None:
    import google.auth.exceptions

    def default(scopes=None):
        raise google.auth.exceptions.DefaultCredentialsError("no credentials found at /secret/path")

    manager = EarthEngineManager("demo-project", ApplicationDefaultEarthEngine(FakeEE(), default))
    with pytest.raises(EarthEngineInitializationError) as exc:
        manager.initialize()
    assert str(exc.value) == "Earth Engine initialization failed"


def test_conflicting_credentials_never_start_earth_engine() -> None:
    fake = FakeEE()
    manager = EarthEngineManager("demo-project", ConflictingEarthEngineConfig(fake))
    with pytest.raises(EarthEngineInitializationError):
        manager.initialize()
    assert fake.calls == []


def test_status_distinguishes_auth_modes_and_does_not_claim_verification(tmp_path) -> None:
    adc = app_client(ee_use_application_default_credentials=True).get("/api/v2/status").json()["earth_engine"]
    assert adc["auth_mode"] == "application_default_credentials"
    assert "Keyless" in adc["auth_description"]
    assert adc["credentials_verified"] is False and adc["initialization"] == "uninitialized"
    conflict = app_client(ee_use_application_default_credentials=True, ee_service_account_key_file=str(tmp_path / "k.json")).get("/api/v2/status").json()
    assert conflict["earth_engine"]["auth_mode"] == "conflicting_configuration"
    assert any(CONFLICT_MESSAGE in w for w in conflict["warnings"])


# --- production settings and documentation ------------------------------------------------


def test_secure_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.trust_proxy_headers is False and s.trusted_proxy_ips is None
    assert s.api_keys is None and s.rate_limit_per_minute == 0
    assert s.ee_service_account_key_file is None and s.ee_use_application_default_credentials is False
    assert s.frontend_dist_dir is None


def test_env_example_documents_every_setting() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, flags=re.MULTILINE))
    missing = {name.upper() for name in Settings.model_fields} - documented
    assert not missing, f"Settings missing from backend/.env.example: {sorted(missing)}"


def test_env_example_matches_current_scientific_defaults() -> None:
    """The example must document the defaults, never silently change scientific thresholds."""
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    values = dict(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=(\S*)", example, flags=re.MULTILINE))
    defaults = Settings(_env_file=None)
    for name in ("trend_min_slope_years", "trend_min_significance_years", "trend_significance_alpha",
                 "trend_min_adjacent_pairs", "trend_material_lag1_rho", "annual_min_represented_months",
                 "annual_min_valid_coverage", "rh_min_annual_coverage", "precipitation_min_valid_months",
                 "soil_moisture_smap_min_valid_days_per_month", "precipitation_region_min_valid_area_fraction"):
        assert float(values[name.upper()]) == float(getattr(defaults, name)), name


def test_lock_file_satisfies_requirement_ranges() -> None:
    from packaging.requirements import Requirement

    pins = {}
    for line in (BACKEND / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            pins[name.lower().replace("_", "-")] = version
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            req = Requirement(line)
            assert req.name.lower() in pins, req.name
            assert req.specifier.contains(pins[req.name.lower()]), (req.name, pins[req.name.lower()])


# --- single-origin serving --------------------------------------------------------------


def test_single_origin_serves_spa_assets_and_api_together(tmp_path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<!doctype html><script type="module" src="/app/assets/index.js"></script>', encoding="utf-8")
    (tmp_path / "assets" / "index.js").write_text("console.log('ok')", encoding="utf-8")
    c = app_client(frontend_dist_dir=str(tmp_path))
    page = c.get("/app/")
    assert page.status_code == 200 and "/app/assets/index.js" in page.text
    asset = c.get("/app/assets/index.js")
    assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
    assert c.get("/api/v2/status").status_code == 200
    assert c.get("/api/v2/variables").status_code == 200
    assert c.get("/docs").status_code == 200
