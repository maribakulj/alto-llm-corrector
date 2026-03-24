"""In-memory job store with SSE fan-out."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncGenerator, Optional

from app.schemas import JobManifest, JobStatus, Provider, SSEEvent


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobManifest] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_job(self, provider: Provider, model: str) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = JobManifest(
            job_id=job_id,
            provider=provider,
            model=model,
        )
        self._subscribers[job_id] = []
        return job_id

    def get_job(self, job_id: str) -> Optional[JobManifest]:
        return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)

    # ------------------------------------------------------------------
    # SSE
    # ------------------------------------------------------------------

    def emit(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        """Push an SSEEvent to all subscriber queues."""
        sse = SSEEvent(event=event, data=data)
        for q in self._subscribers.get(job_id, []):
            try:
                q.put_nowait(sse)
            except asyncio.QueueFull:
                pass  # slow consumer — drop

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id, [])
        try:
            subs.remove(queue)
        except ValueError:
            pass

    async def stream_events(self, job_id: str) -> AsyncGenerator[SSEEvent, None]:
        """
        Yield SSEEvents for job_id.

        Sends a keepalive ping every 30 s.
        Exits when a 'completed' or 'failed' event is received.
        """
        queue = self.subscribe(job_id)
        try:
            while True:
                try:
                    event: SSEEvent = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                    if event.event in ("completed", "failed"):
                        break
                except asyncio.TimeoutError:
                    yield SSEEvent(event="keepalive", data={})
        finally:
            self.unsubscribe(job_id, queue)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

job_store = JobStore()
