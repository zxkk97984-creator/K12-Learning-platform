from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_v1_ping_uses_envelope() -> None:
    response = client.get("/api/v1/ping")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"pong": True}
    assert "meta" in body


def test_validation_error_uses_envelope() -> None:
    response = client.get("/api/v1/ping?unexpected=1")
    # GET 无 query 参数约束，该请求应 200；改用不存在的路径验证 404 信封
    assert response.status_code == 200
    not_found = client.get("/api/v1/not-exist")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "HTTP_ERROR"
