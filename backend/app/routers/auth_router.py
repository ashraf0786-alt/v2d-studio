"""Registration, login and current-user endpoints."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..config import settings
from ..db import get_session
from ..entitlements import is_owner
from ..models import AuthToken, User
from ..notify import send_email
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, session: Session = Depends(get_session)):
    email = str(req.email).lower()
    if session.exec(select(User).where(User.email == email)).first():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        full_name=req.full_name or email.split("@")[0],
        hashed_password=hash_password(req.password),
        is_owner=email in settings.owner_emails,
    )
    session.add(user)
    session.commit()
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)):
    from fastapi import HTTPException
    user = session.exec(select(User).where(User.email == str(req.email).lower())).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return TokenResponse(access_token=create_access_token(user.email))


class TokenConfirm(BaseModel):
    token: str


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: str
    new_password: str


def _make_token(session: Session, user: User, kind: str) -> str:
    plain = secrets.token_urlsafe(32)
    session.add(AuthToken(
        user_id=user.id, token_hash=hashlib.sha256(plain.encode()).hexdigest(),
        kind=kind, expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    session.commit()
    link = f"{settings.PUBLIC_BASE_URL}/auth/{kind}?token={plain}"
    send_email(user.email, f"Your {kind} link", f"Open this link within 24 hours:\n{link}")
    return plain


def _consume(session: Session, plain: str, kind: str) -> AuthToken:
    digest = hashlib.sha256(plain.encode()).hexdigest()
    token = session.exec(select(AuthToken).where(AuthToken.token_hash == digest)).first()
    if not token or token.kind != kind or token.used or token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    token.used = True
    session.add(token)
    return token


@router.post("/verify/send")
def send_verification(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if user.is_verified:
        return {"sent": False, "note": "Already verified"}
    token = _make_token(session, user, "verify")
    result = {"sent": True}
    if not settings.is_production:
        result["dev_token"] = token
    return result


@router.post("/verify/confirm")
def confirm_verification(req: TokenConfirm, session: Session = Depends(get_session)):
    token = _consume(session, req.token, "verify")
    user = session.exec(select(User).where(User.id == token.user_id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    user.is_verified = True
    session.add(user)
    session.commit()
    return {"verified": True}


@router.post("/reset/request")
def request_reset(req: ResetRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == str(req.email).lower())).first()
    if not user:
        return {"sent": False, "note": "If the account exists, a reset link was sent."}
    token = _make_token(session, user, "reset")
    result = {"sent": True}
    if not settings.is_production:
        result["dev_token"] = token
    return result


@router.post("/reset/confirm")
def confirm_reset(req: ResetConfirm, session: Session = Depends(get_session)):
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    token = _consume(session, req.token, "reset")
    user = session.exec(select(User).where(User.id == token.user_id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    user.hashed_password = hash_password(req.new_password)
    session.add(user)
    session.commit()
    return {"reset": True}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id, email=user.email, full_name=user.full_name,
        plan="owner" if is_owner(user) else user.plan,
        is_owner=is_owner(user), created_at=user.created_at,
    )
