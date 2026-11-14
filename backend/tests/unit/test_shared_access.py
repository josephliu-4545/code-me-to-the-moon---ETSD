import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core.access import TokenBucket, cost_for, fingerprint, parse_keys
from app.core.config import Settings
from app.core.earth_engine import EarthEngineInitializationError, EarthEngineManager
from app.core.ee_credentials import (
    ServiceAccountConfigError,
    ServiceAccountEarthEngine,
    auth_mode,
    earth_engine_module,
    key_file_inside,
    read_service_account_email,
)
from app.main import create_app


SECRET = "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"


def key_file(tmp_path: Path, **over) -> str:
    data = {"type": "service_account", "client_email": "estd-backend@example-project.iam.gserviceaccount.com",
            "private_key": SECRET, **over}
    path = tmp_path / "sa.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


class FakeEE:
    def __init__(self) -> None:
        self.calls = []

    def ServiceAccountCredentials(self, email, key_file=None):  # noqa: N802
        self.calls.append(("creds", email, key_file))
        return f"credentials-for-{email}"

    def Initialize(self, credentials=None, project=None):  # noqa: N802
        self.calls.append(("init", credentials, project))

    ImageCollection = "image-collection-attr"


# --- service-account credentials ----------------------------------------------


def test_service_account_initialize_passes_credentials_and_project(tmp_path) -> None:
    fake = FakeEE()
    module = ServiceAccountEarthEngine(key_file(tmp_path), fake)
    module.Initialize(project="demo-project")
    assert fake.calls[0][0] == "creds" and fake.calls[0][1].startswith("estd-backend@")
    assert fake.calls[1] == ("init", "credentials-for-estd-backend@example-project.iam.gserviceaccount.com", "demo-project")
    assert module.ImageCollection == "image-collection-attr"  # other ee attributes delegate


@pytest.mark.parametrize(
    "over, message",
    [({"type": "authorized_user"}, "not a service-account key"), ({"client_email": ""}, "missing client_email"),
     ({"private_key": ""}, "missing client_email or private_key")],
)
def test_malformed_keys_are_rejected_without_leaking_secrets(tmp_path, over, message) -> None:
    with pytest.raises(ServiceAccountConfigError, match=message) as exc:
        read_service_account_email(key_file(tmp_path, **over))
    assert "PRIVATE KEY" not in str(exc.value)


def test_missing_and_invalid_key_files(tmp_path) -> None:
    with pytest.raises(ServiceAccountConfigError, match="readable file"):
        read_service_account_email(str(tmp_path / "nope.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ServiceAccountConfigError, match="not valid JSON"):
        read_service_account_email(str(bad))


def test_manager_sanitises_service_account_failures(tmp_path) -> None:
    manager = EarthEngineManager("demo-project", ServiceAccountEarthEngine(str(tmp_path / "missing.json"), FakeEE()))
    with pytest.raises(EarthEngineInitializationError) as exc:
        manager.initialize()
    assert str(exc.value) == "Earth Engine initialization failed"


def test_auth_mode_and_module_selection(tmp_path) -> None:
    import ee
    assert auth_mode(None) == "local_user_credentials" and earth_engine_module(None) is ee
    assert auth_mode("x.json") == "service_account" and isinstance(earth_engine_module("x.json"), ServiceAccountEarthEngine)
    assert key_file_inside(str(tmp_path / "a" / "k.json"), tmp_path) is True
    assert key_file_inside(str(tmp_path / "k.json"), tmp_path / "other") is False


# --- access keys and rate limiting ------------------------------------------------


def client(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, ee_project_id="test", **settings)))


def test_local_default_has_no_key_or_rate_limit() -> None:
    c = client()
    for _ in range(5):
        assert c.get("/api/v2/variables").status_code == 200


def test_api_key_required_when_configured() -> None:
    c = client(api_keys="team-key-1, team-key-2")
    r = c.get("/api/v2/variables")
    assert r.status_code == 401 and r.json()["detail"]["reason"] == "api_key_required"
    assert "team-key" not in r.text
    assert c.get("/api/v2/variables", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/v2/variables", headers={"X-API-Key": "team-key-2"}).status_code == 200


def test_open_paths_stay_reachable_with_keys() -> None:
    c = client(api_keys="k")
    assert c.get("/").status_code == 200
    assert c.get("/api/v2/status").status_code == 200
    assert c.options("/api/v2/variables").status_code != 401


def test_rate_limit_returns_429_with_retry_after() -> None:
    c = client(rate_limit_per_minute=3)
    codes = [c.get("/api/v2/variables").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = c.get("/api/v2/variables")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert r.json()["detail"]["reason"] == "rate_limited"


def test_cors_headers_present_on_rejections() -> None:
    c = client(api_keys="k")
    r = c.get("/api/v2/variables", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_token_bucket_refills_and_separates_clients() -> None:
    now = [0.0]
    bucket = TokenBucket(60, clock=lambda: now[0])
    assert bucket.take("a", 60) == 0
    assert bucket.take("a") > 0
    assert bucket.take("b") == 0
    now[0] += 1.0
    assert bucket.take("a") == 0
    assert TokenBucket(2, clock=lambda: 0.0).take("c", cost=3) == 0  # cost capped at capacity


def test_helpers() -> None:
    assert parse_keys(" a, ,b ") == ("a", "b") and parse_keys(None) == ()
    assert cost_for("/api/v2/compare") == 3 and cost_for("/api/v2/analysis") == 1
    assert fingerprint("secret") != "secret" and len(fingerprint("secret")) == 16


# --- status endpoint --------------------------------------------------------------------


def test_status_reports_configuration_without_secrets(tmp_path) -> None:
    path = key_file(tmp_path)
    body = client(ee_service_account_key_file=path, api_keys="k", rate_limit_per_minute=30).get("/api/v2/status").json()
    assert body["earth_engine"]["auth_mode"] == "service_account"
    assert body["earth_engine"]["service_account_key_valid"] is True
    assert body["access"] == {"api_key_required": True, "rate_limit_per_minute": 30}
    text = json.dumps(body)
    assert "PRIVATE KEY" not in text and "estd-backend@" not in text and path not in text


def test_status_warns_about_missing_project_and_bad_key(tmp_path) -> None:
    c = TestClient(create_app(Settings(_env_file=None, ee_project_id=None, ee_service_account_key_file=str(tmp_path / "x.json"))))
    body = c.get("/api/v2/status").json()
    assert body["earth_engine"]["project_configured"] is False
    assert body["earth_engine"]["service_account_key_valid"] is False
    assert any("EE_PROJECT_ID" in w for w in body["warnings"])
    assert any("readable file" in w for w in body["warnings"])


def test_status_warns_when_key_is_inside_repository(monkeypatch, tmp_path) -> None:
    from app.api.routes import status as status_route
    monkeypatch.setattr(status_route, "REPO_ROOT", tmp_path)
    body = client(ee_service_account_key_file=key_file(tmp_path)).get("/api/v2/status").json()
    assert any("inside the repository" in w for w in body["warnings"])
