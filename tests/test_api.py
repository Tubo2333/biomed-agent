# tests/test_api.py — REST API tests (structural, no LLM)


import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Create a TestClient with an isolated test database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(
        "src.config.config.storage.db_path", str(db_file)
    )
    monkeypatch.setattr(
        "src.api.main.config.storage.db_path", str(db_file)
    )
    # Prevent background pipeline execution during tests
    async def _noop(tid, q):
        pass
    monkeypatch.setattr(
        "src.api.main._run_pipeline",
        _noop,
    )
    from src.api.main import app
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"


class TestCreateAnalysis:
    def test_create_returns_task_id(self, client):
        resp = client.post("/analysis", json={
            "question": "CSTB in colorectal cancer prognosis"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert len(data["task_id"]) == 12

    def test_empty_question_rejected(self, client):
        resp = client.post("/analysis", json={"question": ""})
        assert resp.status_code == 422  # validation error


class TestGetAnalysis:
    def test_get_existing_task(self, client):
        # Create
        resp = client.post("/analysis", json={
            "question": "Test question"
        })
        tid = resp.json()["task_id"]

        # Get status
        resp2 = client.get(f"/analysis/{tid}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["task_id"] == tid
        assert data["question"] == "Test question"
        assert data["status"] == "pending"

    def test_get_nonexistent(self, client):
        resp = client.get("/analysis/nonexistent")
        assert resp.status_code == 404

    def test_report_unfinished_returns_409(self, client):
        resp = client.post("/analysis", json={
            "question": "Not finished yet"
        })
        tid = resp.json()["task_id"]
        resp2 = client.get(f"/analysis/{tid}/report")
        assert resp2.status_code == 409

    def test_report_completed(self, client):
        # Create and manually mark completed with report
        resp = client.post("/analysis", json={
            "question": "Completed task"
        })
        tid = resp.json()["task_id"]
        from src.storage.db import TaskManager
        from src.config import config
        db = TaskManager(config.storage.db_path)
        db.update_status(tid, "completed")
        db.save_result(tid, "ReportAgent", "report", {"report_text": "# Test Report"})

        resp2 = client.get(f"/analysis/{tid}/report")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["report"] == "# Test Report"


class TestListAndStats:
    def test_list_tasks(self, client):
        r1 = client.post("/analysis", json={"question": "Test Q1"})
        assert r1.status_code == 201, f"Create failed: {r1.json()}"
        r2 = client.post("/analysis", json={"question": "Test Q2"})
        assert r2.status_code == 201, f"Create failed: {r2.json()}"
        resp = client.get("/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1  # At least one created successfully

    def test_stats(self, client):
        r = client.post("/analysis", json={"question": "Stat test"})
        assert r.status_code == 201
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tasks"] >= 1
        assert "avg_duration_ms" in data


class TestCacheHeader:
    def test_cache_header_present(self, client):
        resp = client.get("/health")
        assert "X-Cache" in resp.headers
