"""Unit tests — the 'test' gate of the pipeline. If any fail, CI stops before
building or pushing an image."""
from app import APP_VERSION, app


def _client():
    return app.test_client()


def test_home_reports_app_and_version():
    resp = _client().get("/")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["app"] == "week5-cicd"
    assert body["version"] == APP_VERSION


def test_healthz_ok():
    resp = _client().get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
