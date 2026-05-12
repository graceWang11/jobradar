"""In-process async event bus that powers the SSE stream.

Limitation: events only reach live SSE subscribers when the emitter runs in the
same process as the API server. The CLI pipeline running in a separate process
still persists rows to SQLite, so frontend reconnects pick up the change via
/api/email/status hydration — they just miss the live push.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Set


# Event names must match the frontend reducer in useEmailFeed.ts exactly.
EVENT_EMAIL_SENT = "email.sent"
EVENT_EMAIL_REPLY = "email.reply"
EVENT_FOLLOWUP_SCHEDULED = "followup.scheduled"
EVENT_FOLLOWUP_FIRED = "followup.fired"
EVENT_FOLLOWUP_CANCELLED = "followup.cancelled"
EVENT_THREAD_READ = "thread.read"


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


@dataclass
class Event:
    name: str
    payload: Dict[str, Any]

    def to_sse(self) -> str:
        data = json.dumps(_serialize(self.payload), ensure_ascii=False)
        return f"event: {self.name}\ndata: {data}\n\n"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue[Event]] = set()
        self._pending: List[Event] = []  # events emitted before any loop is running
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup. Sync endpoint handlers run in a thread
        pool where get_running_loop() raises, so emit() needs an explicit
        reference to the server's loop to schedule fan-out from any thread.
        """
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def emit(self, name: str, payload: Dict[str, Any]) -> None:
        """Fan out to every subscriber. Safe to call from sync code."""
        event = Event(name=name, payload=payload)
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._pending.append(event)
                return
        for queue in list(self._subscribers):
            loop.call_soon_threadsafe(self._put_nowait_safe, queue, event)

    def _put_nowait_safe(self, queue: asyncio.Queue[Event], event: Event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop on backpressure; client will rehydrate

    async def drain_pending(self) -> None:
        """Flush events emitted before the loop existed (e.g. at import time)."""
        while self._pending:
            event = self._pending.pop(0)
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def stream(self, keepalive_seconds: float = 15.0) -> AsyncIterator[str]:
        """Async generator yielding SSE-formatted event strings."""
        queue = self.subscribe()
        await self.drain_pending()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self.unsubscribe(queue)


bus = EventBus()
