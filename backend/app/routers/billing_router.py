"""Subscriptions via Stripe, with owner bypass and a local dev-mode upgrade."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import get_current_user, require_owner
from ..config import settings
from ..db import get_session
from ..entitlements import PLAN_LIMITS, can_use_api, is_owner, public_plan
from ..models import ApiKey, User

router = APIRouter(prefix="/api/billing", tags=["billing"])

STRIPE_API = "https://api.stripe.com/v1"


class CheckoutRequest(BaseModel):
    plan: str


def _stripe_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}


@router.get("/plans")
def plans(user: User = Depends(get_current_user)):
    out = []
    for key, lim in PLAN_LIMITS.items():
        out.append({
            "id": key, "label": lim.label, "price_monthly": lim.price_monthly,
            "max_duration_seconds": lim.max_duration_seconds,
            "max_resolution": lim.max_resolution,
            "modes": list(lim.modes), "watermark": lim.watermark,
            "exports": list(lim.exports), "batch": lim.batch, "api_access": lim.api_access,
            "commercial": lim.commercial,
        })
    return {"plans": out, "current": public_plan(user)}


@router.post("/checkout")
def checkout(req: CheckoutRequest, user: User = Depends(get_current_user)):
    if is_owner(user):
        return {"url": None, "message": "Owner accounts have full access — no subscription needed."}
    if req.plan not in ("pro", "studio") or not settings.BILLING_ENABLED or not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Online billing is not configured on this deployment.")
    price = settings.STRIPE_PRICE_PRO if req.plan == "pro" else settings.STRIPE_PRICE_STUDIO
    if not price:
        raise HTTPException(status_code=503, detail=f"No Stripe price configured for {req.plan}.")
    payload = {
        "mode": "subscription",
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
        "success_url": f"{settings.PUBLIC_BASE_URL}/billing?checkout=success",
        "cancel_url": f"{settings.PUBLIC_BASE_URL}/billing?checkout=cancelled",
        "client_reference_id": str(user.id),
        "metadata[user_id]": str(user.id),
    }
    if user.stripe_customer_id:
        payload["customer"] = user.stripe_customer_id
    else:
        payload["customer_email"] = user.email
    with httpx.Client(timeout=20) as client:
        r = client.post(f"{STRIPE_API}/checkout/sessions", data=payload, headers=_stripe_headers())
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=r.text[:300])
    return {"url": r.json()["url"]}


@router.post("/portal")
def portal(user: User = Depends(get_current_user)):
    if not user.stripe_customer_id or not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="No billing account found")
    with httpx.Client(timeout=20) as client:
        r = client.post(
            f"{STRIPE_API}/billing_portal/sessions",
            data={"customer": user.stripe_customer_id,
                  "return_url": f"{settings.PUBLIC_BASE_URL}/billing"},
            headers=_stripe_headers(),
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=r.text[:300])
    return {"url": r.json()["url"]}


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts, v1 = parts.get("t"), parts.get("v1")
    if not ts or not v1:
        return False
    if abs(int(time.time()) - int(ts)) > 300:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@router.post("/webhook")
async def webhook(request: Request, session: Session = Depends(get_session)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if not _verify_stripe_signature(payload, sig, settings.STRIPE_WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(payload)
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})
    customer_id = obj.get("customer")
    user = None
    if customer_id:
        user = session.exec(select(User).where(User.stripe_customer_id == customer_id)).first()
    email = obj.get("customer_email") or obj.get("email")
    if not user and email:
        user = session.exec(select(User).where(User.email == str(email).lower())).first()

    if user:
        price_to_plan = {
            settings.STRIPE_PRICE_PRO: "pro",
            settings.STRIPE_PRICE_STUDIO: "studio",
        }
        if etype in ("checkout.session.completed", "customer.subscription.created",
                     "customer.subscription.updated"):
            price_id = None
            items = obj.get("line_items", {}).get("data") or obj.get("items", {}).get("data") or []
            if items:
                price_id = items[0].get("price", {}).get("id") if isinstance(items[0].get("price"), dict) else items[0].get("price")
            user.plan = price_to_plan.get(price_id, user.plan)
            user.stripe_customer_id = customer_id or user.stripe_customer_id
            session.add(user)
            session.commit()
        elif etype in ("customer.subscription.deleted", "invoice.payment_failed"):
            if not is_owner(user):
                user.plan = "free"
                session.add(user)
                session.commit()
    return {"received": True}


class ApiKeyRequest(BaseModel):
    name: str = "default"


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@router.get("/api-keys")
def list_api_keys(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if not can_use_api(user):
        raise HTTPException(status_code=403, detail="API access requires Studio or Owner")
    keys = session.exec(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False)).all()  # noqa: E712
    return [{"id": k.id, "name": k.name, "prefix": k.key_hash[:8],
             "created_at": k.created_at, "last_used_at": k.last_used_at} for k in keys]


@router.post("/api-keys")
def create_api_key(req: ApiKeyRequest, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    if not can_use_api(user):
        raise HTTPException(status_code=403, detail="API access requires Studio or Owner")
    plain = "v2d_" + secrets.token_urlsafe(32)
    key = ApiKey(user_id=user.id, name=req.name, key_hash=_hash_key(plain))
    session.add(key)
    session.commit()
    return {"id": key.id, "key": plain, "name": key.name,
            "note": "Store this key now — it is shown only once."}


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: int, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    key = session.exec(select(ApiKey).where(ApiKey.id == key_id)).first()
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked = True
    session.add(key)
    session.commit()
    return {"ok": True}


class DevPlanRequest(BaseModel):
    plan: str


@router.post("/dev-plan")
def dev_plan(req: DevPlanRequest, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    """Local development only: switch plans without Stripe. Disabled when billing is on."""
    if settings.BILLING_ENABLED:
        raise HTTPException(status_code=404, detail="Not available in production mode")
    if is_owner(user):
        return {"plan": "owner", "note": "Owner already has full access"}
    if req.plan not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    user.plan = req.plan
    session.add(user)
    session.commit()
    return {"plan": user.plan}
