"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Video to 3D Studio"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development | production
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000"
    RATE_LIMIT_PER_MINUTE: int = 120
    PERSONAL_MODE: bool = True   # no subscriptions; everything free for the owner
    OWNER_PASSWORD: str = "password123"  # used by the personal setup script

    # Database (SQLite by default so it runs anywhere; set a Postgres URL in production)
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Storage
    STORAGE_DIR: Path = Path("./data/storage")
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Auth
    JWT_SECRET: str = "CHANGE_ME_DEV_SECRET_please_set_a_long_random_value"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7
    OWNER_EMAILS: str = ""  # comma separated; these accounts always have full access

    # Billing
    BILLING_ENABLED: bool = False
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_STUDIO: str = ""

    # Queue & storage (horizontal scaling options)
    REDIS_URL: str = ""            # e.g. redis://localhost:6379/0 — enables the durable queue
    QUEUE_BACKEND: str = "auto"    # auto | thread | redis
    STORAGE_BACKEND: str = "local" # local | s3
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"

    # Processing
    MAX_WORKERS: int = 2
    MAX_FRAMES: int = 240          # hard cap on decoded frames per job
    DEFAULT_FPS: int = 12          # sampling rate used for reconstruction
    DEPTH_BACKEND: str = "heuristic"  # "heuristic" | "depth_anything"
    DEPTH_ANYTHING_MODEL: str = "depth-anything/Depth-Anything-V2-Small-hf"
    POSE_LANDMARKER_MODEL: str = ""  # defaults to bundled models/pose_landmarker_lite.task
    POSE_BACKEND: str = "auto"  # auto | mediapipe | demo (auto skips MediaPipe on ARM)

    model_config = ConfigDict(env_file=".env", case_sensitive=True)

    @property
    def queue_backend(self) -> str:
        if self.QUEUE_BACKEND != "auto":
            return self.QUEUE_BACKEND
        return "redis" if self.REDIS_URL else "thread"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def owner_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.OWNER_EMAILS.split(",") if e.strip()}

    @property
    def storage_dir(self) -> Path:
        p = Path(self.STORAGE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def pose_model_path(self) -> Path:
        if self.POSE_LANDMARKER_MODEL:
            return Path(self.POSE_LANDMARKER_MODEL)
        return Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_lite.task"

    @property
    def data_dir(self) -> Path:
        p = Path("./data")
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
