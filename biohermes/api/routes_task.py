"""Task submission and status API routes."""
from __future__ import annotations

import uuid
import asyncio
import json

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/task", tags=["task"])

# Globals set by server.py
_active_sessions: dict = {}
_sse_manager = None
_agent_factory = None


class TaskRequest(BaseModel):
    task: str
    session_id: Optional[str] = None


class TaskResponse(BaseModel):
    session_id: str
    status: str
    message: str


def init(active_sessions: dict, sse_manager, agent_factory):
    global _active_sessions, _sse_manager, _agent_factory
    _active_sessions = active_sessions
    _sse_manager = sse_manager
    _agent_factory = agent_factory


@router.post("", response_model=TaskResponse)
async def submit_task(req: TaskRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id or uuid.uuid4().hex[:16]

    from ..agent.core import BioHermesAgent
    from ..agent.models import TaskStatus
    from .. import config

    sse_queue = _sse_manager.create_queue(session_id)

    agent = BioHermesAgent(
        mineru_api_url=config.MINERU_API_URL,
        on_event=lambda sid, evt, data: _sse_manager.emit(sid, evt, data),
    )

    _active_sessions[session_id] = {
        "status": "pending", "agent": agent, "queue": sse_queue,
    }

    async def run_task():
        session = await agent.run(req.task, session_id=session_id)
        _active_sessions[session_id]["status"] = session.status.value
        _active_sessions[session_id]["result"] = session.to_dict()

    background_tasks.add_task(run_task)

    return TaskResponse(
        session_id=session_id, status="accepted",
        message=f"Task submitted: {req.task[:100]}",
    )


@router.get("/{session_id}")
async def get_task_status(session_id: str):
    if session_id not in _active_sessions:
        raise HTTPException(404, f"Session {session_id} not found")

    info = _active_sessions[session_id]
    if "result" in info:
        return info["result"]
    return {"session_id": session_id, "status": info.get("status", "unknown")}


@router.get("/{session_id}/stream")
async def stream_task(session_id: str):
    from fastapi.responses import StreamingResponse

    if session_id not in _active_sessions:
        raise HTTPException(404, f"Session {session_id} not found")

    queue = _active_sessions[session_id]["queue"]

    async def event_generator():
        yield f"event: connected\ndata: {json.dumps({'session_id': session_id})}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=120)
                event = msg.get("event", "message")
                data = json.dumps(msg.get("data", {}), ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n"
                if event in ("task_complete", "error"):
                    break
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
