# tests/test_storage.py — Database layer tests

import tempfile
from pathlib import Path

from src.storage.db import TaskManager


class TestTaskManager:
    """CRUD operations on SQLite task storage."""

    def setup_method(self):
        import uuid
        self.tmp = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmp) / f"test_{uuid.uuid4().hex[:6]}.db")
        self.db = TaskManager(self.db_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_task(self):
        tid = self.db.create_task("CSTB in colorectal cancer")
        assert len(tid) == 12
        task = self.db.get_task(tid)
        assert task["question"] == "CSTB in colorectal cancer"
        assert task["status"] == "pending"

    def test_update_status(self):
        tid = self.db.create_task("Test question")
        self.db.update_status(tid, "running")
        assert self.db.get_task(tid)["status"] == "running"
        self.db.update_status(tid, "completed")
        assert self.db.get_task(tid)["status"] == "completed"

    def test_update_failed(self):
        tid = self.db.create_task("Will fail")
        self.db.update_status(tid, "failed", error="LLMError: API unreachable")
        task = self.db.get_task(tid)
        assert task["status"] == "failed"
        assert "LLMError" in task["error"]

    def test_set_tokens(self):
        tid = self.db.create_task("Token test")
        self.db.update_status(tid, "completed")
        self.db.set_tokens(tid, 500, 300, 12345)
        task = self.db.get_task(tid)
        assert task["total_tokens_input"] == 500
        assert task["total_tokens_output"] == 300
        assert task["duration_ms"] == 12345

    def test_save_and_get_results(self):
        tid = self.db.create_task("Result test")
        self.db.save_result(tid, "LiteratureAgent", "literature_review", {"papers": 5})
        self.db.save_result(tid, "ReportAgent", "report", {"text": "Hello"})
        results = self.db.get_results(tid)
        assert len(results) == 2
        assert results[0]["agent_name"] == "LiteratureAgent"
        assert results[0]["content"]["papers"] == 5
        assert results[1]["content"]["text"] == "Hello"

    def test_list_tasks(self):
        self.db.create_task("Task A")
        self.db.create_task("Task B")
        tasks = self.db.list_tasks()
        assert len(tasks) == 2

    def test_get_nonexistent(self):
        assert self.db.get_task("nonexistent") is None

    def test_stats(self):
        self.db.create_task("S1")
        tid = self.db.create_task("S2")
        self.db.update_status(tid, "completed")
        self.db.set_tokens(tid, 100, 50, 1000)
        stats = self.db.get_stats()
        assert stats["total_tasks"] == 2
        assert stats["completed"] == 1
        assert stats["total_tokens_input"] == 100
        assert stats["avg_duration_ms"] == 1000
