from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .model_provider import provider_from_environment
from .models import TaskStatus
from .runtime import AgentRuntime
from .store import TaskStore


class CreateTask(BaseModel):
    request: str = Field(min_length=3, max_length=4000)
    requested_by: str = Field(default="portfolio-user", max_length=100)


class ApprovalDecision(BaseModel):
    approved: bool
    reviewer: str = Field(min_length=2, max_length=100)
    comment: str = Field(default="", max_length=500)


def serialize(task) -> dict:
    output = asdict(task)
    output["status"] = task.status.value
    return output


def create_app(database: str | None = None) -> FastAPI:
    store = TaskStore(database or os.getenv("AGENT_DATABASE", "superagent.db"))
    runtime = AgentRuntime(store, provider_from_environment())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.start()
        yield
        await runtime.stop()

    application = FastAPI(title="Industrial SuperAgent Workbench", version="0.1.0", lifespan=lifespan)
    application.state.store = store
    application.state.runtime = runtime

    @application.get("/api/health")
    async def health():
        return {"status": "ok", "queue_depth": runtime.queue.qsize(), "provider": type(runtime.provider).__name__}

    @application.post("/api/tasks", status_code=202)
    async def create_task(body: CreateTask):
        return serialize(await runtime.submit(body.request, {"requested_by": body.requested_by}))

    @application.get("/api/tasks")
    async def list_tasks():
        return [serialize(task) for task in store.list()]

    @application.get("/api/tasks/{task_id}")
    async def get_task(task_id: str):
        try:
            task = store.get(task_id)
        except KeyError:
            raise HTTPException(404, "task not found")
        output = serialize(task)
        output["events"] = store.events(task_id)
        return output

    @application.post("/api/tasks/{task_id}/approval")
    async def approve_task(task_id: str, body: ApprovalDecision):
        try:
            task = store.get(task_id)
            if task.status != TaskStatus.WAITING_APPROVAL:
                raise ValueError("task is not waiting for approval")
            step_id = task.metadata["pending_step"]
            store.decide_approval(task_id, step_id, body.approved, body.reviewer, body.comment)
            await runtime.resume(task_id)
            return {"accepted": True, "task_id": task_id, "step_id": step_id}
        except KeyError:
            raise HTTPException(404, "task not found")
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @application.post("/api/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        try:
            return serialize(await runtime.cancel(task_id))
        except KeyError:
            raise HTTPException(404, "task not found")
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @application.get("/api/tasks/{task_id}/events")
    async def stream_events(task_id: str):
        async def generate():
            cursor = 0
            for _ in range(120):
                for event in store.events(task_id, cursor):
                    cursor = event["seq"]
                    yield f"event: {event['event']}\ndata: {json.dumps(event)}\n\n"
                task = store.get(task_id)
                if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.WAITING_APPROVAL}:
                    break
                await asyncio.sleep(0.5)
        return StreamingResponse(generate(), media_type="text/event-stream")

    web = Path(__file__).with_name("web")
    application.mount("/assets", StaticFiles(directory=web), name="assets")

    @application.get("/")
    async def index():
        return FileResponse(web / "index.html")

    return application


app = create_app()
