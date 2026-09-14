from fastapi.testclient import TestClient

from app.main import app


def test_health_is_versioned() -> None:
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
