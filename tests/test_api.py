"""HTTP contract tests."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_exposes_demo_mode() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "deterministic-demo"}


def test_analyze_returns_trace_and_sql() -> None:
    response = client.post("/api/analyze", json={"question": "按品类看销售额"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "revenue_by_category"
    assert payload["sql"].startswith("SELECT")
    assert payload["verification"]["passed"] is True
    assert payload["metrics"]["model_call_count"] == 0
