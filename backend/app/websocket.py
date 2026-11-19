"""WebSocket endpoint streaming live job progress to the browser."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from .auth import decode_token
from .db import engine
from .entitlements import is_owner
from .models import Job, User
from .progress import hub

router = APIRouter()


@router.websocket("/api/ws/jobs/{job_id}")
async def job_progress(ws: WebSocket, job_id: str, token: str = ""):
    await ws.accept()
    try:
        email = decode_token(token)
    except Exception:
        await ws.send_json({"error": "Unauthorized"})
        await ws.close()
        return

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        job = session.exec(select(Job).where(Job.id == job_id)).first()
    if not user or not job or (job.owner_id != user.id and not is_owner(user)):
        await ws.send_json({"error": "Job not found"})
        await ws.close()
        return

    queue, latest = await hub.subscribe(job_id)
    try:
        if latest:
            await ws.send_json(latest)
        while True:
            event = await queue.get()
            await ws.send_json(event)
            if event.get("status") in ("completed", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(job_id, queue)
