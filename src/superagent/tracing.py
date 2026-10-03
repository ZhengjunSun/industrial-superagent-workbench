from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager


class TraceCollector:
    def __init__(self) -> None:
        self.spans: list[dict] = []

    @asynccontextmanager
    async def span(self, name: str, kind: str, **attributes):
        span = {"span_id": uuid.uuid4().hex[:16], "name": name, "kind": kind, "started_at": time.time(), "attributes": attributes, "status": "ok"}
        try:
            yield span
        except Exception as exc:
            span["status"] = "error"
            span["error_type"] = type(exc).__name__
            raise
        finally:
            span["duration_ms"] = round((time.time() - span["started_at"]) * 1000, 3)
            self.spans.append(span)
