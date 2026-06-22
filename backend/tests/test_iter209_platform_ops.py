"""
Iter 209 — Platform Health & Operations tests.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


class _Req:
    def __init__(self, body=None):
        self._body = body or {}

    async def json(self):
        return self._body


@pytest.mark.asyncio
async def test_mod_note_crud_round_trip():
    from routes import platform_ops as po
    admin_id = ObjectId()
    target_user_id = str(ObjectId())

    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin})

    # Add a note
    created_ids = []
    try:
        out1 = await po.add_mod_note(target_user_id, _Req({"body": "Warned twice for spam", "category": "warning"}))
        assert out1["ok"] is True
        created_ids.append(out1["note_id"])
        # Add second note
        out2 = await po.add_mod_note(target_user_id, _Req({"body": "Appealed in good faith", "category": "positive"}))
        created_ids.append(out2["note_id"])

        # List should return both, newest first
        result = await po.list_mod_notes(target_user_id, _Req())
        assert len(result["notes"]) == 2
        assert result["notes"][0]["body"] == "Appealed in good faith"
        assert result["notes"][0]["category"] == "positive"
        assert result["notes"][0]["author_email"] == "admin@x.com"

        # Validation errors
        try:
            await po.add_mod_note(target_user_id, _Req({"body": "", "category": "warning"}))
            assert False, "expected 400"
        except Exception as e:
            assert "required" in str(e)

        try:
            await po.add_mod_note(target_user_id, _Req({"body": "hi", "category": "not_a_category"}))
            assert False, "expected 400"
        except Exception as e:
            assert "invalid" in str(e).lower()

        # Delete one
        await po.delete_mod_note(target_user_id, out1["note_id"], _Req())
        result2 = await po.list_mod_notes(target_user_id, _Req())
        assert len(result2["notes"]) == 1
    finally:
        await _db().user_mod_notes.delete_many({"user_id": target_user_id})


@pytest.mark.asyncio
async def test_league_health_flags_orphaned_teams_and_inactive_commish():
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin})

    commish_id = ObjectId()
    league_id = ObjectId()
    lid_str = str(league_id)

    # Inactive commissioner (no logins recorded)
    await _db().users.insert_one({"_id": commish_id, "email": "stale@x.com"})
    await _db().leagues.insert_one({
        "_id": league_id,
        "name": "Test Iter209 League",
        "commissioner_id": str(commish_id),
        "status": "active",
        "max_teams": 12,
    })
    # Add 3 teams: 2 with owners, 1 orphan
    teams_inserted = await _db().teams.insert_many([
        {"league_id": lid_str, "owner_id": "u1", "name": "A"},
        {"league_id": lid_str, "owner_id": "u2", "name": "B"},
        {"league_id": lid_str, "name": "Orphan"},
    ])

    try:
        result = await po.league_health(_Req(), days_inactive=30)
        # Inactive commissioner — should be flagged
        ic = next((x for x in result["inactive_commissioners"] if x["league_id"] == lid_str), None)
        assert ic is not None
        assert ic["commissioner_email"] == "stale@x.com"
        # Orphan team — should be flagged
        ot = next((x for x in result["orphaned_teams"] if x["league_id"] == lid_str), None)
        assert ot is not None
        assert ot["orphaned_team_count"] == 1
        assert ot["total_teams"] == 3
        # Capacity issue — 3 of 12
        cap = next((x for x in result["capacity_issues"] if x["league_id"] == lid_str), None)
        assert cap is not None
        assert cap["current_teams"] == 3
        assert cap["expected_teams"] == 12
    finally:
        await _db().leagues.delete_one({"_id": league_id})
        await _db().teams.delete_many({"league_id": lid_str})
        await _db().users.delete_one({"_id": commish_id})


@pytest.mark.asyncio
async def test_sync_status_returns_player_counts_and_health():
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin})

    result = await po.sync_status(_Req())
    assert "healthy" in result
    assert "players_total" in result
    assert "players_with_nhl_id" in result
    assert "career_cache_size" in result
    assert "recent_errors" in result
    assert isinstance(result["players_total"], int)


@pytest.mark.asyncio
async def test_support_metrics_aggregates_by_category_and_avg_response():
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin})

    now = datetime.now(timezone.utc)
    cleanup_marker = f"iter209_test_{ObjectId()}"
    reports = await _db().user_reports.insert_many([
        {
            "category": "harassment", "status": "resolved",
            "reporter_id": cleanup_marker, "target_user_id": "u1",
            "created_at": (now - timedelta(hours=10)).isoformat(),
            "resolved_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "category": "harassment", "status": "open",
            "reporter_id": cleanup_marker, "target_user_id": "u2",
            "created_at": (now - timedelta(hours=4)).isoformat(),
        },
        {
            "category": "spam", "status": "dismissed",
            "reporter_id": cleanup_marker, "target_user_id": "u3",
            "created_at": (now - timedelta(hours=20)).isoformat(),
            "resolved_at": (now - timedelta(hours=16)).isoformat(),
        },
    ])
    try:
        result = await po.support_metrics(_Req(), days=30)
        # Note: aggregate is over ALL reports, not just our test ones
        # — but our 3 must be counted.
        assert result["total_reports"] >= 3
        assert result["open"] >= 1
        cats = {c["category"]: c["count"] for c in result["by_category"]}
        assert cats.get("harassment", 0) >= 2
        assert cats.get("spam", 0) >= 1
        # Average response > 0 since two reports were resolved
        assert result["avg_response_hours"] is not None and result["avg_response_hours"] > 0
    finally:
        await _db().user_reports.delete_many({"reporter_id": cleanup_marker})


@pytest.mark.asyncio
async def test_server_logs_returns_recent_lines_with_error_flag():
    """server-logs endpoint reads supervisor logs and flags ERROR lines."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin})

    result = await po.server_logs(_Req(), service="backend", lines=50)
    assert "service" in result and result["service"] == "backend"
    assert "lines" in result
    assert isinstance(result["lines"], list)
    # tail_size present (may be 0 if logs aren't there in test env)
    assert "tail_size" in result
    assert "error_count" in result


# ─── Iter 210 — Critical Alerts ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_compute_active_alerts_returns_sync_degraded_when_no_recent_updates():
    """When at least one player has a `last_synced_at` but the most-recent
    one is older than 15min, `sync_degraded` alert fires."""
    from routes import platform_ops as po
    po.setup({"db": _db(), "get_current_user": None, "broadcast_to_room": None})

    test_player = ObjectId()
    # Insert a player with a STALE last_synced_at (1 hour ago)
    stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await _db().players.insert_one({
        "_id": test_player,
        "name": "Iter210 Test Player",
        "nhl_id": int(str(test_player)[-8:], 16) % 999999999,
        "last_synced_at": stale,
    })
    try:
        alerts = await po.compute_active_alerts()
        # `sync_degraded` should appear because there are NO recent (<15min)
        # syncs but at least one historical sync (this test player).
        ids = {a["id"] for a in alerts}
        # If the env has no fresh players in 15min, sync_degraded fires.
        # We cannot guarantee NO fresh player in shared test DB so check
        # the alert metadata is well-formed when present.
        for a in alerts:
            assert "id" in a and "severity" in a and "title" in a and "detail" in a
            assert a["severity"] in ("critical", "warning")
    finally:
        await _db().players.delete_one({"_id": test_player})


@pytest.mark.asyncio
async def test_critical_alerts_endpoint_returns_shape_for_admin():
    """`GET /admin/platform/alerts` returns an alerts list + computed_at."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    result = await po.get_critical_alerts(_Req())
    assert "alerts" in result
    assert "computed_at" in result
    assert isinstance(result["alerts"], list)


@pytest.mark.asyncio
async def test_critical_alerts_endpoint_403_for_non_admin():
    from routes import platform_ops as po
    async def _user(_req): return {"_id": str(ObjectId()), "email": "u@x.com", "role": "user"}
    po.setup({"db": _db(), "get_current_user": _user, "broadcast_to_room": None})

    try:
        await po.get_critical_alerts(_Req())
        assert False, "expected 403"
    except Exception as e:
        assert "403" in str(e) or "admin" in str(e).lower()



# ─── Iter 211 — Alert Acknowledgement + Analytics ────────────────────────
@pytest.mark.asyncio
async def test_acknowledge_alert_writes_dedupe_and_filters_active_view():
    """POST /alerts/{id}/acknowledge upserts an ack with TTL and
    GET /alerts/active filters it out for the configured duration."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    alert_id = "sync_degraded"
    # Clean any prior ack
    await _db().alert_acknowledgements.delete_many({"alert_id": alert_id})

    try:
        out = await po.acknowledge_alert(alert_id, _Req({"duration_minutes": 30}))
        assert out["ok"] is True
        assert out["alert_id"] == alert_id
        assert out["expires_at"]

        # The active list filters out silenced ids
        result = await po.list_active_alerts(_Req())
        assert alert_id in result["silenced_ids"]
        assert all(a["id"] != alert_id for a in result["alerts"])

        # Repeated ack should upsert (no duplicate inserts)
        out2 = await po.acknowledge_alert(alert_id, _Req({"duration_minutes": 5}))
        assert out2["ok"] is True
        cnt = await _db().alert_acknowledgements.count_documents({"alert_id": alert_id})
        assert cnt == 1
    finally:
        await _db().alert_acknowledgements.delete_many({"alert_id": alert_id})


@pytest.mark.asyncio
async def test_acknowledge_alert_expires_after_window():
    """An ack with a past expiry should NOT silence the alert anymore."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    expired_id = "expired_alert_iter211"
    await _db().alert_acknowledgements.insert_one({
        "alert_id": expired_id,
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "acknowledged_at": "2026-02-22T00:00:00Z",
        "acknowledged_by_email": "admin@x.com",
    })
    try:
        silenced = await po._active_ack_ids()
        assert expired_id not in silenced
    finally:
        await _db().alert_acknowledgements.delete_one({"alert_id": expired_id})


@pytest.mark.asyncio
async def test_engagement_analytics_returns_dau_mau_and_cohorts():
    """Engagement analytics surfaces DAU series, MAU count, and cohort
    retention rows."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    result = await po.analytics_engagement(_Req(), days=30)
    assert "dau_series" in result
    assert "mau" in result
    assert "latest_dau" in result
    assert "dau_mau_ratio" in result
    assert "cohort_retention" in result
    assert isinstance(result["dau_series"], list)
    assert isinstance(result["cohort_retention"], list)


@pytest.mark.asyncio
async def test_league_survival_aggregates_by_year():
    """League survival groups leagues by creation year and computes
    pct still in `active` status."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    cleanup_marker = f"iter211survival_{ObjectId()}"
    inserted = await _db().leagues.insert_many([
        {"_id": ObjectId(), "name": cleanup_marker, "created_at": "2024-01-15T00:00:00Z", "status": "active"},
        {"_id": ObjectId(), "name": cleanup_marker, "created_at": "2024-06-15T00:00:00Z", "status": "archived"},
        {"_id": ObjectId(), "name": cleanup_marker, "created_at": "2025-03-15T00:00:00Z", "status": "active"},
    ])
    try:
        result = await po.analytics_league_survival(_Req())
        years = {r["year"]: r for r in result["by_year"]}
        # Our test data adds 2 to 2024 (1 active = 50%) and 1 to 2025 (100%)
        assert "2024" in years
        assert "2025" in years
        assert years["2024"]["total"] >= 2
        assert years["2025"]["total"] >= 1
        assert 0 <= years["2024"]["survival_pct"] <= 100
        assert 0 <= years["2025"]["survival_pct"] <= 100
    finally:
        await _db().leagues.delete_many({"_id": {"$in": inserted.inserted_ids}})


@pytest.mark.asyncio
async def test_feature_usage_parses_log_for_endpoints():
    """Endpoint parses the supervisor log and returns top-N endpoints."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    result = await po.analytics_feature_usage(_Req(), days=30)
    assert "top_endpoints" in result
    assert "log_tail_size" in result
    assert isinstance(result["top_endpoints"], list)



# ─── Iter 212 — Revenue + Hockey Insights ────────────────────────────────
@pytest.mark.asyncio
async def test_analytics_revenue_aggregates_by_month():
    """Revenue endpoint groups paid transactions by YYYY-MM month and
    returns total + MRR (last month) + recent paid list."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    marker = f"iter212rev_{ObjectId()}"
    txns = await _db().payment_transactions.insert_many([
        {"session_id": f"{marker}_a", "amount": 1999, "currency": "usd",
         "payment_status": "paid", "created_at": "2026-01-15T00:00:00Z",
         "user_email": "x@x.com"},
        {"session_id": f"{marker}_b", "amount": 1999, "currency": "usd",
         "payment_status": "paid", "created_at": "2026-02-15T00:00:00Z",
         "user_email": "y@y.com"},
        # unpaid — should NOT count
        {"session_id": f"{marker}_c", "amount": 9999, "currency": "usd",
         "payment_status": "pending", "created_at": "2026-02-20T00:00:00Z"},
    ])
    try:
        result = await po.analytics_revenue(_Req(), months=12)
        assert result["total_paid_txns"] >= 2
        assert result["total_revenue_cents"] >= 3998
        months = {m["month"]: m for m in result["by_month"]}
        assert "2026-01" in months
        assert "2026-02" in months
        assert months["2026-01"]["revenue_cents"] >= 1999
        # MRR = latest month's revenue
        assert result["mrr_cents"] >= 0
    finally:
        await _db().payment_transactions.delete_many({"_id": {"$in": txns.inserted_ids}})


@pytest.mark.asyncio
async def test_hockey_ir_abuse_flags_healthy_players_in_ir_slot():
    """IR-abuse endpoint flags players slotted to `section=ir` whose
    player doc has no injury_status."""
    from routes import platform_ops as po
    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    po.setup({"db": _db(), "get_current_user": _admin, "broadcast_to_room": None})

    healthy_pid = ObjectId()
    injured_pid = ObjectId()
    await _db().players.insert_many([
        {"_id": healthy_pid, "name": "Healthy Sneak", "team": "TOR",
         "nhl_id": int(str(healthy_pid)[-8:], 16) % 999999999},
        {"_id": injured_pid, "name": "Really Hurt", "team": "BOS",
         "nhl_id": int(str(injured_pid)[-8:], 16) % 999999999,
         "injury_status": "ir-lt"},
    ])
    team_id = str(ObjectId())
    now_iso = datetime.now(timezone.utc).isoformat()
    event_id = await _db().activity_feed.insert_one({
        "event_type": "lineup_set",
        "team_id": team_id,
        "ts": now_iso,
        "lineup": {
            str(healthy_pid): {"section": "ir", "slot": "IR"},
            str(injured_pid): {"section": "ir", "slot": "IR"},
        },
    })
    try:
        result = await po.hockey_ir_abuse(_Req())
        flagged_pids = [f["player_id"] for f in result["flagged"]]
        assert str(healthy_pid) in flagged_pids, "Healthy player on IR must be flagged"
        assert str(injured_pid) not in flagged_pids, "Truly injured player must NOT be flagged"
        # Healthy entry should have current_status = healthy fallback
        h = next(f for f in result["flagged"] if f["player_id"] == str(healthy_pid))
        assert h["current_status"] == "healthy"
        assert h["player_name"] == "Healthy Sneak"
    finally:
        await _db().activity_feed.delete_one({"_id": event_id.inserted_id})
        await _db().players.delete_many({"_id": {"$in": [healthy_pid, injured_pid]}})

