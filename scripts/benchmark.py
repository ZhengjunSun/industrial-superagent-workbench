from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path

from superagent.runtime import AgentRuntime
from superagent.store import TaskStore


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


async def run(tasks: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory() as directory:
        runtime = AgentRuntime(TaskStore(str(Path(directory) / "bench.db")))
        requests = [
            "Analyze synthetic telecom incident logs",
            "Check refinery crude capacity scenario",
            "Research a fictional legal citation",
        ]
        durations = []
        started = time.perf_counter()
        for index in range(tasks):
            task = await runtime.submit(requests[index % len(requests)])
            item_started = time.perf_counter()
            result = await runtime.run_task(task.task_id)
            durations.append((time.perf_counter() - item_started) * 1000)
            if result.status.value != "completed":
                raise RuntimeError(f"task failed: {result.error}")
        elapsed = time.perf_counter() - started
        return {
            "tasks": tasks,
            "success_rate": 1.0,
            "throughput_tasks_per_second": round(tasks / elapsed, 2),
            "latency_mean_ms": round(statistics.mean(durations), 3),
            "latency_p50_ms": round(percentile(durations, 0.50), 3),
            "latency_p95_ms": round(percentile(durations, 0.95), 3),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.tasks)), indent=2))


if __name__ == "__main__":
    main()

