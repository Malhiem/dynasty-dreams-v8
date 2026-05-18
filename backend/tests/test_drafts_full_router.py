"""Focused unit tests for `routes/drafts.py` — the full draft engine.

Iter 99: bumps `routes/drafts.py` coverage from only the picks endpoint
(5 tests) to all 15 endpoints + the notification helpers + the auction
sub-routes.

The strategy:
- Use the same `isolated_router_app` harness that the other router suites
  use (ephemeral test database, prewired deps).
- Stub `broadcast_to_room` + `log_activity` + `get_current_user` so each
  test is hermetic and runs in <100ms.
- Don't re-test `draft_engine.get_team_for_pick` / `build_draft_board` —
  those are pure functions covered indirectly through the board endpoint.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import drafts as drafts_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


# ─── Helpers ────────────────────────────────────────────────────


async def _seed_league(db, *, commissioner_id="test_user_0001", salary_cap=200):
    res = await db.leagues.insert_one({
        "name": "Draft League",
        "commissioner_id": commissioner_id,
        "salary_cap": salary_cap,
    })
    return str(res.inserted_id)


async def _seed_team(db, *, league_id, name="Cool Team", owner_id="test_user_0001"):
    res = await db.teams.insert_one({
        "league_id": league_id, "name": name, "owner_id": owner_id,
        "owner_name": owner_id,
    })
    return str(res.inserted_id)


async def _seed_player(db, *, name="P", position="C", team="EDM", points=50, **extra):
    doc = {
        "name": name, "position": position, "team": team,
        "team_name": "Edmonton Oilers",
        "points": points, "goals": int(points * 0.4),
        "assists": int(points * 0.6),
        "games_played": 40,
    }
    doc.update(extra)
    res = await db.players.insert_one(doc)
    return str(res.inserted_id)


async def _seed_draft(db, *, league_id, team_abbrs=None, status="scheduled",
                      total_rounds=2, snake=True, draft_type="entry",
                      picks=None, active_auction=None, auction_budgets=None,
                      current_pick=1, timer_paused=False, salary_cap=None):
    doc = {
        "league_id": league_id,
        "league_name": "Draft League",
        "draft_type": draft_type,
        "total_rounds": total_rounds,
        "snake_draft": snake,
        "current_pick": current_pick,
        "status": status,
        "team_abbrs": team_abbrs or ["COOL"],
        "picks": picks or [],
        "chat_messages": [],
        "draft_started": status == "active",
        "timer_paused": timer_paused,
        "team_map": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if active_auction is not None:
        doc["active_auction"] = active_auction
    if auction_budgets is not None:
        doc["auction_budgets"] = auction_budgets
    if salary_cap is not None:
        doc["salary_cap"] = salary_cap
    res = await db.drafts.insert_one(doc)
    return str(res.inserted_id)


def _wire_default_deps():
    """Stub the side-effect deps so the tests don't fan out to push/sockets."""
    drafts_routes._deps["broadcast_to_room"] = _noop_async
    drafts_routes._deps["log_activity"] = _noop_async
    drafts_routes._deps["sio"] = None  # router skips emit if missing
    drafts_routes._deps["calculate_fantasy_points"] = lambda p, c=None: p.get("points", 0)


async def _noop_async(*a, **kw):
    return None


# ═══════════════════════════════════════════════════════════════
# POST /drafts (create)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_draft_404_when_league_missing():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        r = await ctx.client.post("/api/drafts", json={
            "league_id": str(ObjectId()),
            "draft_type": "entry",
            "total_rounds": 5,
        })
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_draft_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER_USER")
        r = await ctx.client.post("/api/drafts", json={
            "league_id": league_id, "draft_type": "entry", "total_rounds": 3,
        })
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_draft_happy_path_seeds_team_abbrs():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen", owner_id="test_user_0001")
        await _seed_team(ctx.db, league_id=league_id, name="Vipers", owner_id="rival")
        r = await ctx.client.post("/api/drafts", json={
            "league_id": league_id, "draft_type": "entry",
            "total_rounds": 3, "snake_draft": True,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "scheduled"
        assert body["current_pick"] == 1
        assert sorted(body["team_abbrs"]) == ["VIPE", "ZARE"]
        # team_map is stripped from the response (it leaks owner_ids)
        assert "team_map" not in body


# ═══════════════════════════════════════════════════════════════
# GET /drafts + GET /drafts/{id} + /board
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_drafts_filters_by_league():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_a = await _seed_league(ctx.db)
        league_b = await _seed_league(ctx.db)
        await _seed_draft(ctx.db, league_id=league_a)
        await _seed_draft(ctx.db, league_id=league_a)
        await _seed_draft(ctx.db, league_id=league_b)
        r = await ctx.client.get(f"/api/drafts?league_id={league_a}")
        body = r.json()
        assert len(body) == 2
        assert all(d["league_id"] == league_a for d in body)


@pytest.mark.asyncio
async def test_get_draft_404_when_missing():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        r = await ctx.client.get(f"/api/drafts/{ObjectId()}")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_draft_board_returns_on_the_clock():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(
            ctx.db, league_id=league_id,
            team_abbrs=["AAA", "BBB", "CCC"], total_rounds=2,
        )
        r = await ctx.client.get(f"/api/drafts/{did}/board")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "scheduled"
        # current_pick=1 → first team
        assert body["on_the_clock"] == "AAA"
        # Board is total_rounds × team_count
        assert len(body["board"]) == 2
        assert len(body["board"][0]) == 3


@pytest.mark.asyncio
async def test_get_draft_board_404_when_missing():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        r = await ctx.client.get(f"/api/drafts/{ObjectId()}/board")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# GET /drafts/{id}/eligible-players
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_eligible_players_excludes_already_drafted():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        p1 = await _seed_player(ctx.db, name="Free", points=80)
        p2 = await _seed_player(ctx.db, name="Drafted", points=90)
        did = await _seed_draft(ctx.db, league_id=league_id, picks=[
            {"player_id": p2, "team": "AAA", "round": 1},
        ])
        r = await ctx.client.get(f"/api/drafts/{did}/eligible-players")
        body = r.json()
        names = [p["name"] for p in body["players"]]
        assert "Free" in names
        assert "Drafted" not in names


@pytest.mark.asyncio
async def test_eligible_players_search_substring():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_player(ctx.db, name="Connor McDavid")
        await _seed_player(ctx.db, name="Sidney Crosby")
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.get(f"/api/drafts/{did}/eligible-players?search=mcdav")
        body = r.json()
        names = [p["name"] for p in body["players"]]
        assert names == ["Connor McDavid"]


@pytest.mark.asyncio
async def test_eligible_players_position_filter():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_player(ctx.db, name="C1", position="C")
        await _seed_player(ctx.db, name="LW1", position="LW")
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.get(f"/api/drafts/{did}/eligible-players?position=LW")
        names = [p["name"] for p in r.json()["players"]]
        assert names == ["LW1"]


# ═══════════════════════════════════════════════════════════════
# POST /drafts/{id}/start
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_start_draft_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.post(f"/api/drafts/{did}/start")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_start_draft_400_when_already_active():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, status="active")
        r = await ctx.client.post(f"/api/drafts/{did}/start")
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_start_draft_happy_path_flips_status_and_pushes_chat():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.post(f"/api/drafts/{did}/start?early_start=true")
        assert r.status_code == 200
        body = r.json()
        assert body["early_start"] is True
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        assert d["status"] == "active"
        assert d["current_pick"] == 1
        assert d["draft_started"] is True
        # System chat message pushed
        assert any("Draft has started" in m["text"] for m in d["chat_messages"])


# ═══════════════════════════════════════════════════════════════
# POST /drafts/{id}/pick
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pick_400_when_draft_not_active():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, status="scheduled")
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_pick_403_when_user_has_no_team():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, status="active",
                                 team_abbrs=["ALPH"])
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_pick_403_when_not_users_turn_and_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        # current user is NOT commissioner, has team ZARE, but ALPH is on the clock
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            team_abbrs=["ALPH", "ZARE"], current_pick=1,
        )
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 403
        assert "ALPH" in r.json()["detail"]


@pytest.mark.asyncio
async def test_pick_commissioner_can_pick_for_any_team():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            team_abbrs=["ALPH", "ZARE"], current_pick=1,
        )
        pid = await _seed_player(ctx.db, name="McDavid")
        # ALPH on clock, current user is commissioner — should succeed
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["overall"] == 1
        assert body["team"] == "ALPH"
        assert body["player"]["name"] == "McDavid"


@pytest.mark.asyncio
async def test_pick_400_when_player_already_drafted():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen")
        pid = await _seed_player(ctx.db)
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            team_abbrs=["ZARE"],
            picks=[{"player_id": pid, "team": "ZARE", "round": 1}],
        )
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 400
        assert "already drafted" in r.json()["detail"]


@pytest.mark.asyncio
async def test_pick_404_when_player_id_invalid():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            team_abbrs=["ZARE"],
        )
        r = await ctx.client.post(f"/api/drafts/{did}/pick",
                                  json={"player_id": str(ObjectId())})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_pick_final_pick_marks_draft_completed():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek Frozen")
        # 1 team x 1 round = 1 total pick
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            team_abbrs=["ZARE"], total_rounds=1,
        )
        pid = await _seed_player(ctx.db)
        r = await ctx.client.post(f"/api/drafts/{did}/pick", json={"player_id": pid})
        assert r.status_code == 200
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        assert d["status"] == "completed"
        # Two extra chat messages (pick + completed)
        assert any("complete" in m["text"].lower() for m in d["chat_messages"])


# ═══════════════════════════════════════════════════════════════
# POST /drafts/{id}/pause
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pause_toggles_timer_state():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, status="active",
                                 timer_paused=False)
        r1 = await ctx.client.post(f"/api/drafts/{did}/pause")
        assert r1.json()["paused"] is True
        # Toggle back
        r2 = await ctx.client.post(f"/api/drafts/{did}/pause")
        assert r2.json()["paused"] is False


@pytest.mark.asyncio
async def test_pause_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        did = await _seed_draft(ctx.db, league_id=league_id, status="active")
        r = await ctx.client.post(f"/api/drafts/{did}/pause")
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# /drafts/{id}/chat (POST + GET)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_chat_pushes_message_with_team_sender():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="My Team")
        did = await _seed_draft(ctx.db, league_id=league_id, status="active")
        r = await ctx.client.post(f"/api/drafts/{did}/chat",
                                  json={"text": "Let's go!"})
        assert r.status_code == 200
        body = r.json()
        assert body["sender"] == "My Team"
        assert body["text"] == "Let's go!"
        assert body["type"] == "chat"


@pytest.mark.asyncio
async def test_get_chat_404_when_missing():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        r = await ctx.client.get(f"/api/drafts/{ObjectId()}/chat")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_chat_returns_messages_array():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id)
        # Push some chat directly to make the test deterministic
        await ctx.db.drafts.update_one(
            {"_id": ObjectId(did)},
            {"$push": {"chat_messages": {
                "id": "a", "type": "chat", "sender": "X", "text": "hi",
            }}},
        )
        r = await ctx.client.get(f"/api/drafts/{did}/chat")
        body = r.json()
        assert len(body) == 1
        assert body[0]["text"] == "hi"


# ═══════════════════════════════════════════════════════════════
# PUT /drafts/{id}/config
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_config_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.put(f"/api/drafts/{did}/config",
                                 json={"time_per_pick": 60})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_config_only_sets_provided_keys():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, total_rounds=2)
        r = await ctx.client.put(f"/api/drafts/{did}/config",
                                 json={"time_per_pick": 90})
        body = r.json()
        assert body["updated"] == ["time_per_pick"]
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        assert d["time_per_pick"] == 90
        assert d["total_rounds"] == 2  # untouched


@pytest.mark.asyncio
async def test_update_config_empty_body_is_noop():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id)
        r = await ctx.client.put(f"/api/drafts/{did}/config", json={})
        assert r.json() == {"updated": []}


# ═══════════════════════════════════════════════════════════════
# Notification helpers (create_notification / notify_league)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_notification_persists_and_broadcasts():
    """The helper inserts a notification row + best-effort sio emit + push.

    Since `sio` is None and `routes.push.send_push` is an async coroutine,
    neither side-effect should raise; the doc lands in MongoDB."""
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        doc = await drafts_routes.create_notification(
            "user_A", "trade_proposed", "T", "M",
            league_id="L1", link="/x",
        )
        assert doc["_id"]
        assert doc["user_id"] == "user_A"
        assert doc["read"] is False
        # Persisted with the right shape
        row = await ctx.db.notifications.find_one({"_id": ObjectId(doc["_id"])})
        assert row["title"] == "T"
        assert row["message"] == "M"
        assert row["league_id"] == "L1"


@pytest.mark.asyncio
async def test_notify_league_fans_out_excludes_self():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="A", owner_id="user_A")
        await _seed_team(ctx.db, league_id=league_id, name="B", owner_id="user_B")
        await _seed_team(ctx.db, league_id=league_id, name="C", owner_id="user_C")
        await drafts_routes.notify_league(
            league_id, "trade_proposed", "T", "M",
            link="/x", exclude_user="user_A",
        )
        rows = await ctx.db.notifications.find({}).to_list(100)
        owners = sorted(r["user_id"] for r in rows)
        assert owners == ["user_B", "user_C"]


# ═══════════════════════════════════════════════════════════════
# Auction routes (nominate / bid / resolve / state / init-budgets)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auction_nominate_400_if_not_auction_draft():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek")
        pid = await _seed_player(ctx.db)
        did = await _seed_draft(ctx.db, league_id=league_id, status="active",
                                 draft_type="entry")
        r = await ctx.client.post(f"/api/drafts/{did}/auction/nominate",
                                  json={"player_id": pid, "opening_bid": 5})
        assert r.status_code == 400
        assert "not an auction" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auction_nominate_400_when_auction_already_in_progress():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Zarek")
        pid = await _seed_player(ctx.db)
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction",
            active_auction={"player_id": "x", "current_bid": 1},
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/nominate",
                                  json={"player_id": pid, "opening_bid": 5})
        assert r.status_code == 400
        assert "already in progress" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auction_nominate_400_insufficient_budget():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, salary_cap=100)
        team_id = await _seed_team(ctx.db, league_id=league_id, name="Z")
        pid = await _seed_player(ctx.db)
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction", salary_cap=100,
            auction_budgets={team_id: 20},
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/nominate",
                                  json={"player_id": pid, "opening_bid": 30})
        assert r.status_code == 400
        assert "Insufficient budget" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auction_nominate_happy_path_sets_active_auction():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id, name="Zarek")
        pid = await _seed_player(ctx.db, name="McDavid", position="C")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction", salary_cap=200,
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/nominate",
                                  json={"player_id": pid, "opening_bid": 25})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player_name"] == "McDavid"
        assert body["current_bid"] == 25
        assert body["nominator_team_id"] == team_id
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        assert d["active_auction"]["player_id"] == pid
        assert len(d["active_auction"]["bid_history"]) == 1


@pytest.mark.asyncio
async def test_auction_bid_400_when_no_active_auction():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Z")
        did = await _seed_draft(ctx.db, league_id=league_id, status="active",
                                 draft_type="auction")
        r = await ctx.client.post(f"/api/drafts/{did}/auction/bid",
                                  json={"amount": 10})
        assert r.status_code == 400
        assert "No active auction" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auction_bid_400_when_not_higher_than_current():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Z")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction",
            active_auction={"player_id": "x", "current_bid": 50,
                            "player_name": "X"},
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/bid",
                                  json={"amount": 30})
        assert r.status_code == 400
        assert "higher than" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auction_bid_happy_path_updates_current_bid_and_pushes_history():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id, name="Z")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction", salary_cap=200,
            active_auction={"player_id": "x", "current_bid": 10,
                            "player_name": "X", "bid_history": []},
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/bid",
                                  json={"amount": 20})
        assert r.status_code == 200, r.text
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        assert d["active_auction"]["current_bid"] == 20
        assert d["active_auction"]["current_bidder_team_id"] == team_id
        assert len(d["active_auction"]["bid_history"]) == 1


@pytest.mark.asyncio
async def test_auction_resolve_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction",
            active_auction={"player_id": "x", "current_bid": 10,
                            "current_bidder_team_id": "t1",
                            "current_bidder_team_name": "T",
                            "player_name": "X", "player_position": "C",
                            "player_team": "EDM"},
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/resolve")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_auction_resolve_happy_path_creates_pick_and_clears_auction():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        team_id = await _seed_team(ctx.db, league_id=league_id, name="Zarek")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction", salary_cap=200,
            auction_budgets={team_id: 200},
            active_auction={
                "player_id": "p1", "current_bid": 35,
                "current_bidder_team_id": team_id,
                "current_bidder_team_name": "Zarek",
                "player_name": "McDavid", "player_position": "C",
                "player_team": "EDM",
            },
        )
        r = await ctx.client.post(f"/api/drafts/{did}/auction/resolve")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["winning_bid"] == 35
        assert body["remaining_budget"] == 165
        d = await ctx.db.drafts.find_one({"_id": ObjectId(did)})
        # Auction cleared
        assert d["active_auction"] is None
        # Pick pushed
        assert len(d["picks"]) == 1
        assert d["picks"][0]["player_id"] == "p1"
        # Budget deducted
        assert d["auction_budgets"][team_id] == 165


@pytest.mark.asyncio
async def test_auction_state_returns_budgets_and_picks_per_team():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db)
        team_a = await _seed_team(ctx.db, league_id=league_id, name="A")
        team_b = await _seed_team(ctx.db, league_id=league_id, name="B")
        did = await _seed_draft(
            ctx.db, league_id=league_id, status="active",
            draft_type="auction", salary_cap=150,
            auction_budgets={team_a: 100, team_b: 130},
            picks=[
                {"team": "A", "player_id": "p1"},
                {"team": "A", "player_id": "p2"},
                {"team": "B", "player_id": "p3"},
            ],
        )
        r = await ctx.client.get(f"/api/drafts/{did}/auction/state")
        body = r.json()
        assert body["draft_type"] == "auction"
        assert body["total_picks"] == 3
        by_team = {b["team_name"]: b for b in body["budgets"]}
        assert by_team["A"]["budget_remaining"] == 100
        assert by_team["A"]["players_won"] == 2
        assert by_team["B"]["players_won"] == 1


@pytest.mark.asyncio
async def test_init_budgets_403_when_not_commissioner():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, commissioner_id="OTHER")
        did = await _seed_draft(ctx.db, league_id=league_id,
                                 draft_type="auction")
        r = await ctx.client.post(f"/api/drafts/{did}/auction/init-budgets")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_init_budgets_seeds_each_team_with_league_cap():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        league_id = await _seed_league(ctx.db, salary_cap=180)
        team_a = await _seed_team(ctx.db, league_id=league_id, name="A")
        team_b = await _seed_team(ctx.db, league_id=league_id, name="B")
        did = await _seed_draft(ctx.db, league_id=league_id,
                                 draft_type="auction")
        r = await ctx.client.post(f"/api/drafts/{did}/auction/init-budgets")
        assert r.status_code == 200
        body = r.json()
        assert body["budgets"][team_a] == 180
        assert body["budgets"][team_b] == 180


# ═══════════════════════════════════════════════════════════════
# GET /drafts/{league_id}/picks   (smoke regression — extracted in iter 91)
# ═══════════════════════════════════════════════════════════════
# Already covered by `test_drafts_router.py`. We just keep the cross-check
# that the router still mounts the path even after iter 98 rewrite.


@pytest.mark.asyncio
async def test_picks_endpoint_still_mounts_after_iter98_rewrite():
    async with isolated_router_app(drafts_routes) as ctx:
        _wire_default_deps()
        r = await ctx.client.get("/api/drafts/unknown-league/picks")
        assert r.status_code == 200
        assert r.json()["picks"] == []
