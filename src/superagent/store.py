from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict

from .models import Step, Task, TaskStatus


class TaskStore:
    def __init__(self, path: str = "superagent.db") -> None:
        self.path = path
        self._lock = threading.RLock()
        self._init_schema()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(
              task_id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
              steps TEXT NOT NULL, cursor INTEGER NOT NULL, result TEXT, error TEXT,
              metadata TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
              event TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals(
              task_id TEXT NOT NULL, step_id TEXT NOT NULL, status TEXT NOT NULL,
              reviewer TEXT, comment TEXT, decided_at REAL,
              PRIMARY KEY(task_id, step_id)
            );
            CREATE TABLE IF NOT EXISTS step_results(
              task_id TEXT NOT NULL, step_id TEXT NOT NULL, result TEXT NOT NULL,
              PRIMARY KEY(task_id, step_id)
            );
            """)

    def create(self, request: str, steps: list[Step], metadata: dict | None = None) -> Task:
        task = Task(uuid.uuid4().hex, request, TaskStatus.QUEUED, steps, metadata=metadata or {})
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)", (
                task.task_id, request, task.status.value, json.dumps([asdict(s) for s in steps]), 0,
                None, None, json.dumps(task.metadata), now, now,
            ))
            self._event(db, task.task_id, "task_created", {"steps": len(steps)})
        return task

    def get(self, task_id: str) -> Task:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return Task(
            row["task_id"], row["request"], TaskStatus(row["status"]),
            [Step(**item) for item in json.loads(row["steps"])], row["cursor"],
            json.loads(row["result"]) if row["result"] else None, row["error"], json.loads(row["metadata"]),
        )

    def list(self, limit: int = 50) -> list[Task]:
        with self._connect() as db:
            ids = [row[0] for row in db.execute("SELECT task_id FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))]
        return [self.get(task_id) for task_id in ids]

    def update(self, task: Task) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE tasks SET status=?,cursor=?,result=?,error=?,metadata=?,updated_at=? WHERE task_id=?", (
                task.status.value, task.cursor, json.dumps(task.result) if task.result is not None else None,
                task.error, json.dumps(task.metadata), time.time(), task.task_id,
            ))
            self._event(db, task.task_id, "checkpoint", {"status": task.status.value, "cursor": task.cursor})

    def save_step_result(self, task_id: str, step_id: str, result: dict) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO step_results VALUES(?,?,?)", (task_id, step_id, json.dumps(result)))
            self._event(db, task_id, "step_completed", {"step_id": step_id})

    def step_result(self, task_id: str, step_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT result FROM step_results WHERE task_id=? AND step_id=?", (task_id, step_id)).fetchone()
        return json.loads(row[0]) if row else None

    def request_approval(self, task_id: str, step_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO approvals(task_id,step_id,status) VALUES(?,?,'pending')", (task_id, step_id))
            self._event(db, task_id, "approval_requested", {"step_id": step_id})

    def decide_approval(self, task_id: str, step_id: str, approved: bool, reviewer: str, comment: str = "") -> None:
        with self._lock, self._connect() as db:
            changed = db.execute(
                "UPDATE approvals SET status=?,reviewer=?,comment=?,decided_at=? WHERE task_id=? AND step_id=? AND status='pending'",
                ("approved" if approved else "rejected", reviewer, comment, time.time(), task_id, step_id),
            ).rowcount
            if not changed:
                raise ValueError("approval is not pending")
            self._event(db, task_id, "approval_decided", {"step_id": step_id, "approved": approved, "reviewer": reviewer})

    def approval(self, task_id: str, step_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT status FROM approvals WHERE task_id=? AND step_id=?", (task_id, step_id)).fetchone()
        return row[0] if row else None

    def events(self, task_id: str, after: int = 0) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT seq,event,payload,created_at FROM events WHERE task_id=? AND seq>? ORDER BY seq", (task_id, after)).fetchall()
        return [{"seq": r["seq"], "event": r["event"], "payload": json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows]

    @staticmethod
    def _event(db: sqlite3.Connection, task_id: str, event: str, payload: dict) -> None:
        db.execute("INSERT INTO events(task_id,event,payload,created_at) VALUES(?,?,?,?)", (task_id, event, json.dumps(payload), time.time()))
