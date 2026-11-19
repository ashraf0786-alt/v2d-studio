"""Storage abstraction: local filesystem by default, optional S3-compatible object store."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .config import settings


def _safe_name(name: str) -> str:
    base = Path(name or "upload").name
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
    return safe or "upload"


def user_dir(user_id: int) -> Path:
    p = settings.storage_dir / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_dir(user_id: int, job_id: str) -> Path:
    p = user_dir(user_id) / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(user_id: int, job_id: str, filename: str, data: bytes) -> Path:
    d = job_dir(user_id, job_id)
    path = d / ("input_" + _safe_name(filename))
    with open(path, "wb") as f:
        f.write(data)
    return path


def remove_job(user_id: int, job_id: str) -> None:
    d = user_dir(user_id) / job_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    if settings.STORAGE_BACKEND == "s3":
        for key in list_objects(user_id, job_id):
            delete_object(key)


def artifact_url(user_id: int, job_id: str, filename: str) -> str:
    return f"{settings.PUBLIC_BASE_URL}/api/files/{user_id}/{job_id}/{filename}"


def new_job_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# S3-compatible storage (optional)
# ---------------------------------------------------------------------------

def _s3_client():  # pragma: no cover - requires boto3 + credentials
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def _key(user_id: int, job_id: str, filename: str) -> str:
    return f"{user_id}/{job_id}/{filename}"


def sync_to_s3(user_id: int, job_id: str) -> int:  # pragma: no cover
    """Upload all artifacts for a finished job to the object store."""
    if settings.STORAGE_BACKEND != "s3":
        return 0
    client = _s3_client()
    count = 0
    for path in job_dir(user_id, job_id).iterdir():
        if path.is_file():
            client.upload_file(str(path), settings.S3_BUCKET, _key(user_id, job_id, path.name))
            count += 1
    return count


def get_local_path(user_id: int, job_id: str, filename: str) -> Path | None:
    """Return a local path for a file, fetching from S3 into the cache if needed."""
    safe = _safe_name(filename)
    local = job_dir(user_id, job_id) / safe
    if local.exists():
        return local
    if settings.STORAGE_BACKEND == "s3":  # pragma: no cover
        try:
            client = _s3_client()
            client.download_file(settings.S3_BUCKET, _key(user_id, job_id, safe), str(local))
            return local
        except Exception:
            return None
    return None


def list_objects(user_id: int, job_id: str) -> list[str]:  # pragma: no cover
    if settings.STORAGE_BACKEND != "s3":
        return []
    client = _s3_client()
    prefix = f"{user_id}/{job_id}/"
    resp = client.list_objects_v2(Bucket=settings.S3_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]


def delete_object(key: str) -> None:  # pragma: no cover
    _s3_client().delete_object(Bucket=settings.S3_BUCKET, Key=key)
