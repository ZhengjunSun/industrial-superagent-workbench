import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from superagent.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(str(Path(self.temp.name) / "api.db")))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_health_and_task_lifecycle(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        created = self.client.post("/api/tasks", json={"request": "Research a fictional legal citation"})
        self.assertEqual(created.status_code, 202)
        task_id = created.json()["task_id"]
        for _ in range(30):
            state = self.client.get(f"/api/tasks/{task_id}").json()
            if state["status"] == "completed":
                break
            time.sleep(0.02)
        self.assertEqual(state["status"], "completed")
        self.assertTrue(state["events"])

    def test_unknown_task(self):
        self.assertEqual(self.client.get("/api/tasks/missing").status_code, 404)
