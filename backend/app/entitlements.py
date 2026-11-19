"""Plan limits and the single source of truth for access checks.

Every gate in the app goes through `check_access`, which applies the owner
bypass first. This is what makes "everything free for the owner" true across
all modes and platforms, while public accounts are metered by their plan.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from .config import settings
from .models import User

PLANS = ("free", "pro", "studio")


@dataclass(frozen=True)
class PlanLimits:
    label: str
    price_monthly: int
    max_duration_seconds: int
    max_resolution: int              # longest edge in pixels
    modes: tuple[str, ...]
    priority: int
    watermark: bool
    exports: tuple[str, ...]
    batch: bool
    api_access: bool
    commercial: bool


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        label="Free",
        price_monthly=0,
        max_duration_seconds=10,
        max_resolution=720,
        modes=("parallax",),
        priority=0,
        watermark=True,
        exports=("webm",),
        batch=False,
        api_access=False,
        commercial=False,
    ),
    "pro": PlanLimits(
        label="Pro",
        price_monthly=19,
        max_duration_seconds=60,
        max_resolution=1080,
        modes=("parallax", "mocap", "scene"),
        priority=1,
        watermark=False,
        exports=("webm", "mp4", "glb", "ply", "bvh", "json"),
        batch=False,
        api_access=False,
        commercial=True,
    ),
    "studio": PlanLimits(
        label="Studio",
        price_monthly=79,
        max_duration_seconds=120,
        max_resolution=2160,
        modes=("parallax", "mocap", "scene"),
        priority=2,
        watermark=False,
        exports=("webm", "mp4", "glb", "ply", "bvh", "json"),
        batch=True,
        api_access=True,
        commercial=True,
    ),
}

OWNER_LIMITS = PlanLimits(
    label="Owner (unlimited)",
    price_monthly=0,
    max_duration_seconds=10**9,
    max_resolution=10**5,
    modes=("parallax", "mocap", "scene"),
    priority=3,
    watermark=False,
    exports=tuple(PLAN_LIMITS["studio"].exports),
    batch=True,
    api_access=True,
    commercial=True,
)


def can_use_api(user: User) -> bool:
    return limits_for(user).api_access


def can_batch(user: User) -> bool:
    return limits_for(user).batch


def is_owner(user: User) -> bool:
    return user.is_owner or user.email.lower() in settings.owner_emails


def limits_for(user: User) -> PlanLimits:
    if is_owner(user):
        return OWNER_LIMITS
    return PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])


def public_plan(user: User) -> dict:
    """Return a serializable plan description for account/billing UI."""
    lim = limits_for(user)
    return {
        "plan": "owner" if is_owner(user) else user.plan,
        "label": lim.label,
        "price_monthly": lim.price_monthly,
        "max_duration_seconds": lim.max_duration_seconds,
        "max_resolution": lim.max_resolution,
        "modes": list(lim.modes),
        "priority": lim.priority,
        "watermark": lim.watermark,
        "exports": list(lim.exports),
        "batch": lim.batch,
        "api_access": lim.api_access,
        "commercial": lim.commercial,
        "billing_enabled": settings.BILLING_ENABLED,
        "personal_mode": settings.PERSONAL_MODE,
    }


def check_access(user: User, *, mode: str, duration_seconds: float, resolution: int = 720,
                 export_format: str | None = None) -> None:
    """Raise HTTP 402/403 if the request exceeds the user's entitlements.

    Owner accounts short-circuit every check.
    """
    lim = limits_for(user)
    if mode not in lim.modes:
        raise HTTPException(
            status_code=403,
            detail=f"The '{mode}' mode requires an upgrade. Your plan: {lim.label}.",
        )
    if duration_seconds > lim.max_duration_seconds:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Video is {duration_seconds:.1f}s but your plan allows "
                f"{lim.max_duration_seconds}s. Upgrade to process longer videos."
            ),
        )
    if resolution > lim.max_resolution:
        raise HTTPException(
            status_code=402,
            detail=f"Resolution {resolution}px exceeds your plan limit of {lim.max_resolution}px.",
        )
    if export_format and export_format not in lim.exports:
        raise HTTPException(
            status_code=403,
            detail=f"Export format '{export_format}' is not available on your plan.",
        )
