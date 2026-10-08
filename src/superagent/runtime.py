from __future__ import annotations

import asyncio
import re

from .model_provider import ModelProvider, OfflineProvider
from .models import Step, Task, TaskStatus
from .skills import Skill, default_skills
from .store import TaskStore
from .tracing import TraceCollector


class AgentRuntime:
    def __init__(self, store: TaskStore, provider: ModelProvider | None = None, skills: dict[str, Skill] | None = None) -> None:
        self.store = store
        self.provider = provider or OfflineProvider()
        self.skills = skills or default_skills()
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    def plan(self, request: str) -> list[Step]:
        text = request.lower()
        steps: list[Step] = []
        if any(word in text for word in ("telecom", "通信", "log", "日志", "incident")):
            steps.append(Step("telecom-analysis", "telecom", "build_timeline", {}))
            if any(word in text for word in ("change", "修复", "remediate")):
                steps.append(Step("change-proposal", "telecom", "propose_change", {"requested": request}, risk="high"))
        if any(word in text for word in ("refinery", "炼厂", "crude", "原油")):
            steps.append(Step("refinery-check", "refinery", "check_scenario", {"demand": 100, "capacity": 120}))
        if any(word in text for word in ("legal", "法律", "检察", "citation")):
            steps.append(Step("legal-research", "legal", "research", {"question": request}))
        if not steps:
            steps.append(Step("general-analysis", "legal", "research", {"question": request}))
        return steps

    async def submit(self, request: str, metadata: dict | None = None) -> Task:
        task = self.store.create(request, self.plan(request), metadata)
        await self.queue.put(task.task_id)
        return task

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop())
        for task in self.store.list(200):
            if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                await self.queue.put(task.task_id)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def resume(self, task_id: str) -> None:
        await self.queue.put(task_id)

    async def cancel(self, task_id: str) -> Task:
        task = self.store.get(task_id)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            raise ValueError("terminal task cannot be cancelled")
        task.status = TaskStatus.CANCELLED
        self.store.update(task)
        return task

    async def run_task(self, task_id: str) -> Task:
        task = self.store.get(task_id)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
            return task
        task.status = TaskStatus.RUNNING
        self.store.update(task)
        trace = TraceCollector()
        outputs: list[dict] = list(task.metadata.get("outputs", []))
        try:
            while task.cursor < len(task.steps):
                task = self.store.get(task_id)
                if task.status == TaskStatus.CANCELLED:
                    return task
                step = task.steps[task.cursor]
                existing = self.store.step_result(task_id, step.step_id)
                if existing is not None:
                    outputs.append(existing)
                    task.cursor += 1
                    self.store.update(task)
                    continue
                if step.risk == "high":
                    decision = self.store.approval(task_id, step.step_id)
                    if decision not in {"approved", "rejected"}:
                        self.store.request_approval(task_id, step.step_id)
                        task.status = TaskStatus.WAITING_APPROVAL
                        task.metadata["pending_step"] = step.step_id
                        self.store.update(task)
                        return task
                    if decision == "rejected":
                        task.status = TaskStatus.FAILED
                        task.error = "high-risk step rejected"
                        self.store.update(task)
                        return task
                skill = self.skills[step.skill]
                tool = skill.tools[step.action]
                last_error = None
                for attempt in range(step.max_retries + 1):
                    try:
                        async with trace.span(step.step_id, "tool", skill=step.skill, action=step.action, attempt=attempt + 1):
                            result = await tool(step.arguments)
                        self.store.save_step_result(task_id, step.step_id, result)
                        outputs.append(result)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                if last_error:
                    raise last_error
                task.cursor += 1
                task.metadata["outputs"] = outputs
                task.metadata["trace"] = trace.spans
                self.store.update(task)
            async with trace.span("synthesis", "model"):
                summary = await self.provider.complete([{"role": "user", "content": task.request}, {"role": "system", "content": str(outputs)}])
            task.status = TaskStatus.COMPLETED
            task.result = {"summary": re.sub(r"(?i)(api[_-]?key|password)\s*[=:]\s*\S+", r"\1=[REDACTED]", summary), "outputs": outputs, "artifacts": ["audit.json"]}
            task.metadata["trace"] = trace.spans
            self.store.update(task)
            return task
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = f"{type(exc).__name__}: {exc}"
            task.metadata["trace"] = trace.spans
            self.store.update(task)
            return task

    async def _worker_loop(self) -> None:
        while True:
            task_id = await self.queue.get()
            try:
                await self.run_task(task_id)
            finally:
                self.queue.task_done()
