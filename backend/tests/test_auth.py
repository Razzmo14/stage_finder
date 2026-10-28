"""Auth contract tests for the session-token middleware (ADR 0001).

Every request without a valid Bearer token must be rejected with 401,
including /health and unknown routes.
"""

from fastapi.testclient import TestClient

from app.core import config
from app.main import create_app

TOKEN = "test-session-token"


def make_client(token: str | None = TOKEN) -> TestClient:
    return TestClient(create_app(session_token=token))


def auth(value: str) -> dict[str, str]:
    return {"Authorization": value}


def test_health_rejects_missing_token() -> None:
    response = make_client().get("/health")
    assert response.status_code == 401


def test_health_rejects_wrong_token() -> None:
    response = make_client().get("/health", headers=auth("Bearer wrong-token"))
    assert response.status_code == 401


def test_health_rejects_wrong_scheme() -> None:
    response = make_client().get("/health", headers=auth(f"Basic {TOKEN}"))
    assert response.status_code == 401


def test_health_accepts_valid_token() -> None:
    response = make_client().get("/health", headers=auth(f"Bearer {TOKEN}"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_rejects_missing_token() -> None:
    response = make_client().get("/api/v1/does-not-exist")
    assert response.status_code == 401


def test_unknown_route_with_valid_token_is_404() -> None:
    response = make_client().get("/api/v1/does-not-exist", headers=auth(f"Bearer {TOKEN}"))
    assert response.status_code == 404


def test_no_token_configured_rejects_everything() -> None:
    response = make_client(token=None).get("/health", headers=auth(f"Bearer {TOKEN}"))
    assert response.status_code == 401


def test_token_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("STAGE_FINDER_SESSION_TOKEN", "env-token")
    config.get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers=auth("Bearer env-token")).status_code == 200
    finally:
        config.get_settings.cache_clear()
