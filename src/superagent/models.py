from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Step:
    step_id: str
    skill: str
    action: str
    arguments: dict
    risk: str = "low"
    max_retries: int = 1


@dataclass
class Task:
    task_id: str
    request: str
    status: TaskStatus
    steps: list[Step]
    cursor: int = 0
    result: dict | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
