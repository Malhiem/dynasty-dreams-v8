"""Expo Push Notifications service + routes.

Backend responsibilities:
  - POST /api/push/register-token: store the Expo push token per user.
  - DELETE /api/push/tokens/{token_id}: deactivate a token (e.g. on logout).
  - send_push(user_ids, title, body, data): helper used by crown/chat/roster flows.

Uses Expo's managed push service — no FCM/APNs keys needed.
  https://exp.host/--/api/v2/push/send
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}
_log = logging.getLogger("push")

EXPO_PUSH_ENDPOINT = "https://exp.host/--/api/v2/push/send"
_semaphore = asyncio.Semaphore(6)  # Expo recommends ≤6 concurrent connections


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ────────────────────────────────────────────────
class PushTokenRegister(BaseModel):
    expo_push_token: str
    platform: Optional[str] = Field(default="unknown")
    device_name: Optional[str] = None


# ─── Core sender ─────────────────────────────────────────────
async def _send_batch(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Send a batch of ≤100 push messages to Expo. Returns the ticket list."""
    if not messages:
        return []
    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    EXPO_PUSH_ENDPOINT,
                    json=messages,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip, deflate",
                        "Content-Type": "application/json",
                    },
                )
                if r.status_code != 200:
                    _log.warning(f"Expo push non-200: {r.status_code} {r.text[:500]}")
                    return []
                body = r.json()
                return body.get("data", []) or []
        except Exception as exc:
            _log.warning(f"Expo push error: {exc}")
            return []


async def send_push(
    user_ids: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    sound: str = "default",
) -> Dict[str, Any]:
    """Send a push notification to every active token belonging to user_ids.

    Safe to call from any flow — always swallows exceptions and logs.
    Returns {"tickets": [...], "tokens_count": N}.
    """
    db = _deps.get("db")
    if db is None or not user_ids:
        return {"tickets": [], "tokens_count": 0}

    try:
        cursor = db.push_tokens.find(
            {"user_id": {"$in": [str(uid) for uid in user_ids]}, "is_active": True},
            {"expo_push_token": 1, "user_id": 1},
        )
        tokens = []
        async for doc in cursor:
            tok = doc.get("expo_push_token")
            if tok and tok.startswith("ExponentPushToken"):
                tokens.append(tok)
        if not tokens:
            return {"tickets": [], "tokens_count": 0}

        messages = [
            {
                "to": t,
                "sound": sound,
                "title": title[:120],
                "body": body[:240],
                "data": data or {},
                "priority": "high",
            }
            for t in tokens
        ]
        tickets: list = []
        for i in range(0, len(messages), 100):
            tickets.extend(await _send_batch(messages[i:i + 100]))

        # Handle DeviceNotRegistered → deactivate the token
        for tick, original in zip(tickets, tokens):
            if isinstance(tick, dict) and tick.get("status") == "error":
                details = (tick.get("details") or {}) if isinstance(tick.get("details"), dict) else {}
                err_code = details.get("error")
                if err_code == "DeviceNotRegistered":
                    await db.push_tokens.update_one(
                        {"expo_push_token": original},
                        {"$set": {"is_active": False, "deactivated_at": datetime.now(timezone.utc)}},
                    )

        return {"tickets": tickets, "tokens_count": len(tokens)}
    except Exception as exc:
        _log.warning(f"send_push failed: {exc}")
        return {"tickets": [], "tokens_count": 0}


# ─── Endpoints ───────────────────────────────────────────────
@router.post("/push/register-token")
async def register_push_token(input: PushTokenRegister, request: Request):
    """Register or refresh the current user's Expo push token."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]

    user = await get_current_user(request)
    if not input.expo_push_token.startswith("ExponentPushToken"):
        raise HTTPException(status_code=400, detail="Invalid Expo push token format")

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": str(user["_id"]),
        "expo_push_token": input.expo_push_token,
        "platform": input.platform or "unknown",
        "device_name": input.device_name or None,
        "is_active": True,
        "updated_at": now,
    }
    # Upsert — same token → refresh; new token → insert
    await db.push_tokens.update_one(
        {"expo_push_token": input.expo_push_token},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    saved = await db.push_tokens.find_one(
        {"expo_push_token": input.expo_push_token},
        {"expo_push_token": 0},  # never return the raw token in response
    )
    return {
        "token_id": str(saved["_id"]) if saved else None,
        "user_id": str(user["_id"]),
        "platform": input.platform,
        "is_active": True,
    }


@router.delete("/push/tokens/{token_id}")
async def deactivate_push_token(token_id: str, request: Request):
    """Mark a push token inactive (called on logout or token rotation)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    try:
        oid = ObjectId(token_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token id")

    res = await db.push_tokens.update_one(
        {"_id": oid, "user_id": str(user["_id"])},
        {"$set": {"is_active": False, "deactivated_at": datetime.now(timezone.utc)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Token not found or not owned by you")
    return {"deactivated": True}


@router.get("/push/my-tokens")
async def list_my_push_tokens(request: Request):
    """Return the count + platforms of active tokens for the current user (for debugging)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    cursor = db.push_tokens.find(
        {"user_id": str(user["_id"]), "is_active": True},
        {"expo_push_token": 0},  # never surface raw token
    )
    tokens = []
    async for t in cursor:
        tokens.append({
            "id": str(t["_id"]),
            "platform": t.get("platform"),
            "device_name": t.get("device_name"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
        })
    return {"active_count": len(tokens), "tokens": tokens}


@router.post("/push/test")
async def send_test_push(request: Request):
    """Send a test push to the current user (dev/debug)."""
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    res = await send_push(
        [str(user["_id"])],
        title="Dynasty Dreams",
        body="Push notifications are working! 🏒",
        data={"type": "test"},
    )
    return {"sent": True, "tokens_count": res["tokens_count"]}
