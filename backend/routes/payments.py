"""Stripe payment routes — extracted from server.py (iter 98).

Endpoints:
    POST /api/payments/create               — create a Stripe checkout session
    GET  /api/payments/status/{session_id}  — poll status + grant subscription
    POST /api/webhook/stripe                — Stripe webhook handler

These were previously inline in server.py. Wiring uses the standard
`setup(deps)` pattern shared by every other extracted router.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest,
)


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _logger(): return _deps["logger"]
async def _get_user(request): return await _deps["get_current_user"](request)
def _safe_object_id(value, label="id"): return _deps["_safe_object_id"](value, label)
async def _log_activity(*a, **kw): return await _deps["log_activity"](*a, **kw)


# ─── Models / catalogue ──────────────────────────────────────────


class PaymentCreate(BaseModel):
    package_type: str  # "premium_monthly", "premium_yearly", "league_fee", "league_premium"
    league_id: Optional[str] = None
    origin_url: str


# Payment packages (server-side only — do NOT trust client-supplied amounts)
PAYMENT_PACKAGES = {
    "premium_monthly": {"amount": 9.99, "name": "Premium Monthly"},
    "premium_yearly":  {"amount": 79.99, "name": "Premium Yearly"},
    "league_fee":      {"amount": 0.0, "name": "League Entry Fee"},  # dynamic
    "league_premium":  {"amount": 29.99, "name": "League Premium Unlock"},
}

# Features that flip on when league_premium is purchased
LEAGUE_PREMIUM_FEATURES = [
    {"id": "salary_cap", "name": "Dynasty Salary Cap",
     "description": "Full AAV contracts, NTC/NMC clauses, cap tracking"},
    {"id": "contracts", "name": "Multi-Year Contracts",
     "description": "Issue 1–8 year deals with escalators and bonuses"},
    {"id": "draft_scheduling", "name": "Advanced Draft Scheduling",
     "description": "Auto-schedule snake/auction/rookie drafts with reminders"},
    {"id": "minor_leagues", "name": "Minor League / Farm System",
     "description": "Taxi squad + prospect development slots"},
    {"id": "custom_scoring", "name": "Custom Scoring Profiles",
     "description": "Build your own point values per stat"},
    {"id": "activity_webhooks", "name": "Activity Webhooks",
     "description": "Push every trade/waiver to Discord, Slack, or a custom URL"},
]


def _stripe_client(request: Request) -> StripeCheckout:
    """Build a configured StripeCheckout for this request. The webhook URL is
    derived from the request's `base_url` so it works in preview + production
    without env-specific config."""
    api_key = os.environ.get("STRIPE_API_KEY")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    return StripeCheckout(api_key=api_key, webhook_url=webhook_url)


# ─── Endpoints ───────────────────────────────────────────────────


@router.get("/leagues/{league_id}/premium")
async def get_league_premium(league_id: str, request: Request):
    """Return premium status + feature list for a league."""
    db = _db()
    await _get_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {
        "league_id": league_id,
        "premium": bool(league.get("premium", False)),
        "activated_at": (
            league.get("premium_activated_at").isoformat()
            if league.get("premium_activated_at") else None
        ),
        "price_usd": PAYMENT_PACKAGES["league_premium"]["amount"],
        "features": LEAGUE_PREMIUM_FEATURES,
        "unlocked_features": league.get("premium_features", []),
    }


@router.post("/payments/create")
async def create_checkout(input: PaymentCreate, request: Request):
    db = _db()
    user = await _get_user(request)

    if input.package_type not in PAYMENT_PACKAGES:
        raise HTTPException(status_code=400, detail="Invalid package type")

    package = PAYMENT_PACKAGES[input.package_type]
    amount = package["amount"]

    # League-fee: pull the amount off the league record (server-trusted)
    if input.package_type == "league_fee" and input.league_id:
        league = await db.leagues.find_one({"_id": _safe_object_id(input.league_id, "league_id")})
        if not league or not league.get("entry_fee"):
            raise HTTPException(status_code=400, detail="League has no entry fee")
        amount = float(league["entry_fee"])

    # League-premium: commissioner-only, league must not already be premium
    if input.package_type == "league_premium":
        if not input.league_id:
            raise HTTPException(status_code=400, detail="league_id is required for league_premium")
        league = await db.leagues.find_one({"_id": _safe_object_id(input.league_id, "league_id")})
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        if league["commissioner_id"] != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the commissioner can upgrade this league")
        if league.get("premium"):
            raise HTTPException(status_code=400, detail="League is already premium")

    stripe_checkout = _stripe_client(request)
    success_url = f"{input.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{input.origin_url}/payment/cancel"

    checkout_request = CheckoutSessionRequest(
        amount=amount, currency="usd",
        success_url=success_url, cancel_url=cancel_url,
        metadata={
            "user_id": user["_id"],
            "package_type": input.package_type,
            "league_id": input.league_id or "",
        },
    )
    session = await stripe_checkout.create_checkout_session(checkout_request)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user["_id"],
        "email": user["email"],
        "amount": amount,
        "currency": "usd",
        "package_type": input.package_type,
        "league_id": input.league_id,
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    return {"url": session.url, "session_id": session.session_id}


@router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if transaction["user_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    stripe_checkout = _stripe_client(request)

    # Don't fail the poll just because the upstream lookup hiccuped — clients
    # keep polling so an "unknown" status is recoverable.
    try:
        status = await stripe_checkout.get_checkout_status(session_id)
    except Exception as e:
        _logger().warning(f"Stripe status lookup failed for {session_id}: {e}")
        return {
            "status": "unknown",
            "payment_status": transaction.get("payment_status", "pending"),
            "amount": float(transaction.get("amount", 0.0)),
            "currency": transaction.get("currency", "usd"),
        }

    # Persist any status change and run the post-payment side-effects exactly
    # once (idempotent on `transaction["payment_status"] != "paid"`).
    if status.payment_status != transaction["payment_status"]:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": status.payment_status,
                      "updated_at": datetime.now(timezone.utc)}},
        )

        if status.payment_status == "paid" and transaction["payment_status"] != "paid":
            ptype = transaction["package_type"]
            if ptype in ("premium_monthly", "premium_yearly"):
                await db.users.update_one(
                    {"_id": ObjectId(transaction["user_id"])},
                    {"$set": {
                        "subscription": ptype,
                        "subscription_updated_at": datetime.now(timezone.utc),
                    }},
                )
            elif ptype == "league_premium" and transaction.get("league_id"):
                await db.leagues.update_one(
                    {"_id": ObjectId(transaction["league_id"])},
                    {"$set": {
                        "premium": True,
                        "premium_activated_at": datetime.now(timezone.utc),
                        "premium_features": [f["id"] for f in LEAGUE_PREMIUM_FEATURES],
                    }},
                )
                await _log_activity(
                    transaction["league_id"],
                    "league_premium_unlocked",
                    "Premium features unlocked for this league",
                    transaction["user_id"],
                )

    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount": status.amount_total / 100,
        "currency": status.currency,
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    db = _db()
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    stripe_checkout = _stripe_client(request)
    try:
        event = await stripe_checkout.handle_webhook(body, signature)
        if event.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"session_id": event.session_id},
                {"$set": {"payment_status": "paid",
                          "updated_at": datetime.now(timezone.utc)}},
            )
        return {"status": "ok"}
    except Exception as e:
        _logger().error(f"Webhook error: {e}")
        return {"status": "error"}
