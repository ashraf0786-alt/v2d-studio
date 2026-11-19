"""Thread-safe progress event bus for WebSocket subscribers."""
from __future__ import annotations

import asyncio
import threading
from typing import Any


class ProgressHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._latest: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self, job_id: str) -> tuple[asyncio.Queue, dict[str, Any] | None]:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, set()).add(q)
            latest = self._latest.get(job_id)
        return q, dict(latest) if latest else None

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id)
            if subs:
                subs.discard(q)
                if not subs:
                    self._subscribers.pop(job_id, None)

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        """May be called from any thread (e.g. a worker thread)."""
        if not event.get("from_redis"):
            from .config import settings
            if settings.queue_backend == "redis" and settings.REDIS_URL:
                try:
                    from .queue import publish as redis_publish
                    redis_publish(event)
                except Exception:
                    pass
        with self._lock:
            self._latest[job_id] = dict(event)
            subs = list(self._subscribers.get(job_id, ()))
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._fanout, subs, event)

    def _fanout(self, subs: list[asyncio.Queue], event: dict[str, Any]) -> None:
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


hub = ProgressHub()
