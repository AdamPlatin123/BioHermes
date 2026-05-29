"""SSE event manager for streaming task progress."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional


class SSEManager:
    """Manages SSE event queues for active sessions."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    def create_queue(self, session_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues[session_id] = q
        return q

    def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(session_id)

    def emit(self, session_id: str, event: str, data: dict):
        q = self._queues.get(session_id)
        if q:
            try:
                asyncio.get_event_loop().create_task(q.put({"event": event, "data": data}))
            except RuntimeError:
                pass

    def cleanup(self, session_id: str):
        self._queues.pop(session_id, None)

    def active_sessions(self) -> int:
        return len(self._queues)
