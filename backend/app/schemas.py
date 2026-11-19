"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    plan: str
    is_owner: bool
    created_at: datetime


class JobCreateResponse(BaseModel):
    id: str
    status: str
    message: str


class JobResponse(BaseModel):
    id: str
    mode: str
    status: str
    progress: int
    message: str
    input_filename: str
    output_filename: Optional[str] = None
    duration_seconds: float
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProgressEvent(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
