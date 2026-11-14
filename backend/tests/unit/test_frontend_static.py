from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_built_frontend_is_served_at_app_when_configured(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ESTD</title>", encoding="utf-8")
    client = TestClient(create_app(Settings(_env_file=None, ee_project_id="test", frontend_dist_dir=str(tmp_path))))
    r = client.get("/app/")
    assert r.status_code == 200 and "ESTD" in r.text
    assert client.get("/").json()["status"] == "ok"


def test_frontend_is_not_served_when_not_configured() -> None:
    client = TestClient(create_app(Settings(_env_file=None, ee_project_id="test")))
    assert client.get("/app/").status_code == 404
