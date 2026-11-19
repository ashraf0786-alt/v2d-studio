"""Job creation, listing, downloading and demo generation."""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlmodel import Session, select

from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..entitlements import can_batch, check_access, is_owner, limits_for
from ..jobs import manager
from ..models import Job, User
from ..processing.video import make_sample_video, probe_duration, probe_resolution
from ..schemas import JobCreateResponse, JobResponse, UrlImportRequest
from ..storage import artifact_url, job_dir, new_job_id, save_upload

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ARTIFACT_KEYS = {"video", "keyframe", "depth", "camera_path", "pose", "point_cloud",
                 "scene_depth", "meta", "scene_meta", "glb", "bvh"}


def _to_response(job: Job, user: User, token: str = "") -> JobResponse:
    suffix = f"?token={token}" if token else ""
    result = None
    if job.result_json:
        try:
            raw = json.loads(job.result_json)
            def _artifact(v):
                if isinstance(v, str) and "/" not in v and not v.startswith("http"):
                    return artifact_url(user.id, job.id, v) + suffix
                return v

            result = {}
            for k, v in raw.items():
                if k in ARTIFACT_KEYS and isinstance(v, str):
                    result[k] = artifact_url(user.id, job.id, v) + suffix
                elif isinstance(v, dict):
                    result[k] = {kk: _artifact(vv) for kk, vv in v.items()}
                else:
                    result[k] = v
        except Exception:
            result = None
    return JobResponse(
        id=job.id, mode=job.mode, status=job.status, progress=job.progress,
        message=job.message, input_filename=job.input_filename,
        output_filename=job.output_filename, duration_seconds=job.duration_seconds,
        result=result, error=job.error, created_at=job.created_at, updated_at=job.updated_at,
    )


def _create_job(
    session: Session,
    user: User,
    data: bytes,
    filename: str,
    mode: str,
    max_width: int,
) -> Job:
    lim = limits_for(user)
    if mode not in lim.modes:
        raise HTTPException(status_code=403, detail=f"Mode '{mode}' requires an upgrade")
    job_id = new_job_id()
    d = job_dir(user.id, job_id)
    input_path = save_upload(user.id, job_id, filename, data)
    duration = probe_duration(input_path)
    resolution = probe_resolution(input_path)
    check_access(user, mode=mode, duration_seconds=duration, resolution=resolution)

    if max_width > lim.max_resolution:
        max_width = lim.max_resolution

    job = Job(
        id=job_id, owner_id=user.id, mode=mode, status="queued",
        message="Queued", input_filename=filename, duration_seconds=round(duration, 2),
        parameters_json=json.dumps({
            "max_width": max_width,
            "watermark": lim.watermark,
            "priority": lim.priority,
            "exports": list(lim.exports),
        }),
    )
    session.add(job)
    session.commit()
    manager.submit(job_id, user.id, mode, input_path, json.loads(job.parameters_json))
    return job


@router.post("/upload", response_model=JobCreateResponse)
async def upload_job(
    file: UploadFile = File(...),
    mode: str = Form("parallax"),
    max_width: int = Form(720),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if mode not in {"parallax", "mocap", "scene"}:
        raise HTTPException(status_code=400, detail="Invalid mode")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 500 MB)")
    job = _create_job(session, user, data, file.filename or "video.mp4", mode, max_width)
    return JobCreateResponse(id=job.id, status=job.status, message=job.message)


@router.post("/url", response_model=JobCreateResponse)
def import_url(req: UrlImportRequest,
               user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    """Import a video from any public URL (direct, signed, share link, or platform)."""
    from ..url_import import UrlImportError, _validate_url, url_fingerprint
    lim = limits_for(user)
    if req.mode not in lim.modes:
        raise HTTPException(status_code=403, detail=f"Mode '{req.mode}' requires an upgrade")
    try:
        _validate_url(req.url)
    except UrlImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if len(req.url) > 2048:
        raise HTTPException(status_code=400, detail="URL too long")

    job_id = new_job_id()
    params = {
        "max_width": min(req.max_width, lim.max_resolution),
        "watermark": lim.watermark,
        "priority": lim.priority,
        "exports": list(lim.exports),
        "source_url": req.url,
        "source_fingerprint": url_fingerprint(req.url, req.headers),
    }
    job = Job(
        id=job_id, owner_id=user.id, mode=req.mode, status="queued",
        message="Fetching URL…", input_filename=req.url[:200],
        duration_seconds=0.0, parameters_json=json.dumps(params),
    )
    session.add(job)
    session.commit()
    manager.submit_url(job_id, user.id, req.mode, req.url, req.headers, params)
    return JobCreateResponse(id=job_id, status=job.status, message=job.message)


@router.post("/batch")
async def batch_jobs(
    files: list[UploadFile] = File(...),
    mode: str = Form("parallax"),
    max_width: int = Form(720),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Submit multiple videos at once (Studio/Owner). Per-file failures are reported individually."""
    if not can_batch(user):
        raise HTTPException(status_code=403, detail="Batch processing requires Studio or Owner")
    if mode not in {"parallax", "mocap", "scene"}:
        raise HTTPException(status_code=400, detail="Invalid mode")
    if not 1 <= len(files) <= 10:
        raise HTTPException(status_code=400, detail="Submit between 1 and 10 files")

    created, errors = [], []
    for f in files:
        data = await f.read()
        try:
            if not data:
                raise ValueError("Empty file")
            job = _create_job(session, user, data, f.filename or "video.mp4", mode, max_width)
            created.append({"id": job.id, "filename": job.input_filename, "status": job.status})
        except HTTPException as e:
            errors.append({"filename": f.filename, "error": e.detail})
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)[:200]})
    session.commit()
    return {"created": created, "errors": errors}


@router.post("/demo", response_model=JobCreateResponse)
def demo_job(
    mode: str = Form("parallax"),
    seconds: int = Form(8),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Generate a synthetic sample clip and run it through the pipeline.

    Lets anyone try the product instantly without uploading a file. The clip is
    capped at the user's plan limit, and owner accounts get the full 20s demo.
    """
    lim = limits_for(user)
    seconds = max(3, min(seconds, min(20, lim.max_duration_seconds if lim.max_duration_seconds < 1000 else 20)))
    d = job_dir(user.id, new_job_id())
    input_path = d / "demo.mp4"
    make_sample_video(input_path, seconds=seconds)
    data = input_path.read_bytes()
    job = _create_job(session, user, data, "demo.mp4", mode, 720)
    return JobCreateResponse(id=job.id, status=job.status, message=job.message)


@router.get("", response_model=list[JobResponse])
def list_jobs(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    stmt = select(Job).order_by(Job.created_at.desc()).limit(100)
    if not is_owner(user):
        stmt = select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).limit(100)
    jobs = session.exec(stmt).all()
    return [_to_response(j, user, token) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    job = session.exec(select(Job).where(Job.id == job_id)).first()
    if not job or (job.owner_id != user.id and not is_owner(user)):
        raise HTTPException(status_code=404, detail="Job not found")
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    return _to_response(job, user, token)


@router.delete("/{job_id}")
def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    from ..storage import remove_job
    job = session.exec(select(Job).where(Job.id == job_id)).first()
    if not job or (job.owner_id != user.id and not is_owner(user)):
        raise HTTPException(status_code=404, detail="Job not found")
    session.delete(job)
    session.commit()
    remove_job(job.owner_id, job_id)
    return {"ok": True}


