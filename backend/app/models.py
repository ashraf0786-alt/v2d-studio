"""SQLModel database models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str = ""
    hashed_password: str
    plan: str = Field(default="free", index=True)  # free | pro | studio
    is_owner: bool = Field(default=False)
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    owner_id: int = Field(index=True)
    mode: str  # parallax | mocap | scene
    status: str = Field(default="queued", index=True)  # queued|running|completed|failed
    progress: int = Field(default=0)
    message: str = Field(default="Queued")
    input_filename: str = ""
    output_filename: Optional[str] = None
    duration_seconds: float = 0.0
    parameters_json: str = "{}"
    result_json: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AuthToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    token_hash: str = Field(index=True)
    kind: str  # verify | reset
    expires_at: datetime
    used: bool = Field(default=False)


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    name: str = "default"
    key_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: Optional[datetime] = None
    revoked: bool = Field(default=False)


class UsageEvent(SQLModel, table=True):
    """Audit log of processed seconds, used for metering/quota reporting."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    job_id: str = Field(index=True)
    seconds: float = 0.0
    mode: str = ""
    created_at: datetime = Field(default_factory=utcnow)
