"""Owner-only administration endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from ..auth import get_current_user, require_owner
from ..config import settings
from ..db import get_session
from ..entitlements import is_owner
from ..models import Job, UsageEvent, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def users(session: Session = Depends(get_session), _: User = Depends(require_owner)):
    rows = session.exec(select(User)).all()
    return [{
        "id": u.id, "email": u.email, "plan": u.plan,
        "is_owner": is_owner(u), "active": u.is_active,
    } for u in rows]


class UpdateUser(BaseModel):
    plan: str | None = None
    is_owner: bool | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: int, req: UpdateUser, session: Session = Depends(get_session),
                _: User = Depends(require_owner)):
    u = session.exec(select(User).where(User.id == user_id)).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if req.plan is not None:
        u.plan = req.plan
    if req.is_owner is not None:
        u.is_owner = req.is_owner
    if req.is_active is not None:
        u.is_active = req.is_active
    session.add(u)
    session.commit()
    return {"ok": True}


@router.get("/stats")
def stats(session: Session = Depends(get_session), _: User = Depends(require_owner)) -> dict[str, Any]:
    total_users = session.exec(select(func.count(User.id))).one()
    total_jobs = session.exec(select(func.count(Job.id))).one()
    minutes = session.exec(select(func.coalesce(func.sum(UsageEvent.seconds), 0.0))).one()
    by_status = {}
    for status in ("queued", "running", "completed", "failed"):
        by_status[status] = session.exec(
            select(func.count(Job.id)).where(Job.status == status)
        ).one()
    return {
        "users": total_users, "jobs": total_jobs,
        "processed_minutes": round(float(minutes) / 60.0, 1),
        "by_status": by_status,
        "billing_enabled": settings.BILLING_ENABLED,
    }
