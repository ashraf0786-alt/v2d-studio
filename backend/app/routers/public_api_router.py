"""Key-authenticated REST API for Studio/Owner accounts."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlmodel import Session, select

from ..db import get_session
from ..entitlements import can_use_api, is_owner
from ..models import ApiKey, User
from ..schemas import JobCreateResponse, JobResponse
from .jobs_router import _create_job, _to_response

router = APIRouter(prefix="/api/v1", tags=["public-api"])


def api_user(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> User:
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    key = session.exec(select(ApiKey).where(ApiKey.key_hash == digest,
                                            ApiKey.revoked == False)).first()  # noqa: E712
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    user = session.exec(select(User).where(User.id == key.user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not can_use_api(user):
        raise HTTPException(status_code=403, detail="API access requires Studio or Owner")
    key.last_used_at = datetime.now(timezone.utc)
    session.add(key)
    session.commit()
    return user


def _with_key(job: JobResponse, key: str) -> dict:
    data = job.model_dump()
    if data.get("result"):
        for k, v in list(data["result"].items()):
            if isinstance(v, str) and "/api/files/" in v and "?" not in v:
                data["result"][k] = f"{v}?api_key={key}"
    return data


@router.post("/jobs", response_model=JobCreateResponse)
async def create_job(
    file: UploadFile = File(...),
    mode: str = Form("parallax"),
    max_width: int = Form(720),
    user: User = Depends(api_user),
    session: Session = Depends(get_session),
):
    if mode not in {"parallax", "mocap", "scene"}:
        raise HTTPException(status_code=400, detail="Invalid mode")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    job = _create_job(session, user, data, file.filename or "video.mp4", mode, max_width)
    return JobCreateResponse(id=job.id, status=job.status, message=job.message)


@router.get("/jobs")
def list_jobs(user: User = Depends(api_user), session: Session = Depends(get_session),
              x_api_key: str = Header(..., alias="X-API-Key")):
    from ..models import Job
    stmt = select(Job).order_by(Job.created_at.desc()).limit(100)
    if not is_owner(user):
        stmt = stmt.where(Job.owner_id == user.id)
    jobs = session.exec(stmt).all()
    return [_with_key(_to_response(j, user), x_api_key) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(api_user), session: Session = Depends(get_session),
            x_api_key: str = Header(..., alias="X-API-Key")):
    from ..models import Job
    job = session.exec(select(Job).where(Job.id == job_id)).first()
    if not job or (job.owner_id != user.id and not is_owner(user)):
        raise HTTPException(status_code=404, detail="Job not found")
    return _with_key(_to_response(job, user), x_api_key)
