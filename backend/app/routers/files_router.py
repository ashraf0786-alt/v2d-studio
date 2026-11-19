"""Artifact file route. Accepts a JWT query token so <img>/<video>/3D loaders work."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..auth import decode_token
from ..db import get_session
from ..entitlements import is_owner
from ..models import User
from ..storage import get_local_path

router = APIRouter(prefix="/api/files", tags=["files"])


def _user_from_token(token: str, session: Session, api_key: str = "") -> User | None:
    if token:
        try:
            email = decode_token(token)
            return session.exec(select(User).where(User.email == email)).first()
        except Exception:
            return None
    if api_key:
        import hashlib
        from ..models import ApiKey
        digest = hashlib.sha256(api_key.encode()).hexdigest()
        key = session.exec(select(ApiKey).where(ApiKey.key_hash == digest,
                                                ApiKey.revoked == False)).first()  # noqa: E712
        if key:
            return session.exec(select(User).where(User.id == key.user_id)).first()
    return None


@router.get("/{user_id}/{job_id}/{filename}")
def get_file(user_id: int, job_id: str, filename: str, token: str = "", api_key: str = "",
             session: Session = Depends(get_session)):
    user = _user_from_token(token, session, api_key)
    if not user or (user.id != user_id and not is_owner(user)):
        raise HTTPException(status_code=403, detail="Forbidden")
    path = get_local_path(user_id, job_id, Path(filename).name)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
