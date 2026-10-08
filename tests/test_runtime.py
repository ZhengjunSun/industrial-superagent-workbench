import asyncio
import tempfile
import unittest
from pathlib import Path

from superagent.models import TaskStatus
from superagent.runtime import AgentRuntime
from superagent.store import TaskStore


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(str(Path(self.temp.name) / "test.db"))
        self.runtime = AgentRuntime(self.store)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_multidomain_task_completes(self):
        task = self.store.create("Analyze telecom logs, refinery capacity and legal citations", self.runtime.plan("telecom refinery legal"))
        result = await self.runtime.run_task(task.task_id)
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(len(result.result["outputs"]), 3)

    async def test_high_risk_step_pauses_and_resumes(self):
        task = self.store.create("Analyze telecom incident and propose change", self.runtime.plan("telecom incident change"))
        paused = await self.runtime.run_task(task.task_id)
        self.assertEqual(paused.status, TaskStatus.WAITING_APPROVAL)
        step = paused.metadata["pending_step"]
        self.store.decide_approval(task.task_id, step, True, "tester")
        completed = await self.runtime.run_task(task.task_id)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)

    async def test_pending_approval_remains_blocked_after_restart(self):
        task = self.store.create("telecom change", self.runtime.plan("telecom change"))
        paused = await self.runtime.run_task(task.task_id)
        step = paused.metadata["pending_step"]
        restarted = AgentRuntime(TaskStore(str(Path(self.temp.name) / "test.db")))
        for runtime in (self.runtime, self.runtime, restarted):
            result = await runtime.run_task(task.task_id)
            self.assertEqual(result.status, TaskStatus.WAITING_APPROVAL)
            self.assertEqual(result.cursor, paused.cursor)
            self.assertIsNone(self.store.step_result(task.task_id, step))
        self.store.decide_approval(task.task_id, step, True, "tester")
        self.assertEqual((await restarted.run_task(task.task_id)).status, TaskStatus.COMPLETED)

    async def test_rejected_step_fails_safely(self):
        task = self.store.create("telecom change", self.runtime.plan("telecom change"))
        paused = await self.runtime.run_task(task.task_id)
        self.store.decide_approval(task.task_id, paused.metadata["pending_step"], False, "tester")
        result = await self.runtime.run_task(task.task_id)
        self.assertEqual(result.status, TaskStatus.FAILED)

    async def test_completed_step_is_idempotent(self):
        task = self.store.create("legal research", self.runtime.plan("legal research"))
        first = await self.runtime.run_task(task.task_id)
        events_before = len(self.store.events(task.task_id))
        second = await self.runtime.run_task(task.task_id)
        self.assertEqual(second.status, TaskStatus.COMPLETED)
        self.assertEqual(events_before, len(self.store.events(task.task_id)))
