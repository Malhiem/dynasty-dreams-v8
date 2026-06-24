"""Iter 229 — Default minor-eligible auto-placement.

Tests `_resolve_minor_auto_section` end-to-end + a high-level smoke test
of the add-to-roster endpoint that the helper feeds into.
"""
from __future__ import annotations

import pytest
from bson import ObjectId

from routes import roster as roster_routes
from routes.roster import _resolve_minor_auto_section

from tests.router_test_utils import isolated_router_app, seed_league, seed_team, seed_player


@pytest.mark.asyncio
async def test_helper_returns_none_when_league_has_no_minors_pool():
    league = {"minors_spots": 0}
    player = {"player_type": "prospect"}
    team = {"lineup": {}}
    assert _resolve_minor_auto_section(league, player, team) is None


@pytest.mark.asyncio
async def test_helper_returns_minors_for_explicit_prospect():
    league = {"minors_spots": 5}
    player = {"player_type": "prospect", "position": "C"}
    team = {"lineup": {}}
    assert _resolve_minor_auto_section(league, player, team) == "minors"


@pytest.mark.asyncio
async def test_helper_returns_minors_for_minor_eligible_flag():
    league = {"minors_spots": 5}
    player = {"minor_eligible": True, "position": "LW"}
    team = {"lineup": {}}
    assert _resolve_minor_auto_section(league, player, team) == "minors"


@pytest.mark.asyncio
async def test_helper_returns_minors_for_age_and_gp_under_defaults():
    league = {"minors_spots": 5}
    # 21-year-old with 10 career games — meets the 22-age / 25-GP defaults.
    player = {
        "birth_date": "2004-06-15",
        "career_games_played": 10,
        "position": "C",
    }
    team = {"lineup": {}}
    assert _resolve_minor_auto_section(league, player, team) == "minors"


@pytest.mark.asyncio
async def test_helper_rejects_veteran_by_age_and_gp():
    league = {"minors_spots": 5}
    player = {
        "birth_date": "1995-06-15",  # 30 yrs old
        "career_games_played": 800,
        "position": "C",
    }
    team = {"lineup": {}}
    assert _resolve_minor_auto_section(league, player, team) is None


@pytest.mark.asyncio
async def test_helper_respects_minors_pool_capacity():
    league = {"minors_spots": 2}
    player = {"player_type": "prospect", "position": "RW"}
    team = {"lineup": {
        "p1": {"section": "minors", "slot": "MIN"},
        "p2": {"section": "minors", "slot": "MIN"},
    }}
    assert _resolve_minor_auto_section(league, player, team) is None


@pytest.mark.asyncio
async def test_helper_respects_split_skater_pool_cap():
    league = {
        "minors_spots": 4,
        "minors_split_enabled": True,
        "minors_skater_spots": 1,
        "minors_goalie_spots": 3,
    }
    skater = {"player_type": "prospect", "position": "C"}
    team = {"lineup": {
        "s1": {"section": "minors", "slot": "MIN"},  # 1/1 skaters used
    }}
    assert _resolve_minor_auto_section(league, skater, team) is None
    # but a goalie still slots in
    goalie = {"player_type": "prospect", "position": "G", "primary_position": "G"}
    assert _resolve_minor_auto_section(league, goalie, team) == "minors"


@pytest.mark.asyncio
async def test_helper_respects_split_goalie_pool_cap():
    league = {
        "minors_spots": 4,
        "minors_split_enabled": True,
        "minors_skater_spots": 3,
        "minors_goalie_spots": 1,
    }
    goalie = {"player_type": "prospect", "position": "G", "primary_position": "G"}
    team = {"lineup": {
        "g1": {"section": "minors", "slot": "MIN_G"},  # 1/1 goalies used
    }}
    assert _resolve_minor_auto_section(league, goalie, team) is None


@pytest.mark.asyncio
async def test_add_endpoint_writes_minors_lineup_for_prospect():
    """End-to-end: POST /api/roster/{team_id}/add for a minor-eligible
    prospect should write a `{section: minors, slot: MIN}` lineup entry
    on the team.
    """
    async with isolated_router_app(roster_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"minors_spots": 10, "roster_spots": 20}},
        )
        team_id = await seed_team(ctx.db, league_id=league_id)
        prospect_id = await seed_player(ctx.db, name="Tynan Lawrence", position="C")
        await ctx.db.players.update_one(
            {"_id": ObjectId(prospect_id)},
            {"$set": {"player_type": "prospect", "minor_eligible": True}},
        )
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add",
            json={"player_id": prospect_id},
        )
        assert r.status_code == 200, r.text
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert prospect_id in (team.get("roster") or [])
        lineup = team.get("lineup") or {}
        slot = lineup.get(prospect_id)
        assert slot is not None, "prospect should have a lineup entry"
        assert slot["section"] == "minors"
        assert slot["slot"] == "MIN"


@pytest.mark.asyncio
async def test_add_endpoint_skips_auto_placement_for_veteran():
    """Veteran adds shouldn't touch the lineup — Minors auto-placement
    must be opt-in (eligibility-gated)."""
    async with isolated_router_app(roster_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"minors_spots": 10, "roster_spots": 20}},
        )
        team_id = await seed_team(ctx.db, league_id=league_id)
        vet_id = await seed_player(ctx.db, name="Sidney Crosby", position="C")
        await ctx.db.players.update_one(
            {"_id": ObjectId(vet_id)},
            {"$set": {"birth_date": "1987-08-07", "career_games_played": 1200}},
        )
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add",
            json={"player_id": vet_id},
        )
        assert r.status_code == 200, r.text
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        assert vet_id in (team.get("roster") or [])
        # No lineup entry should have been auto-stamped.
        assert not (team.get("lineup") or {}).get(vet_id)


@pytest.mark.asyncio
async def test_add_endpoint_goalie_uses_min_g_slot():
    """A minor-eligible goalie should auto-place into the goalie minors
    slot (MIN_G) so the lineup matrix renders it correctly."""
    async with isolated_router_app(roster_routes) as ctx:
        league_id = await seed_league(ctx.db)
        await ctx.db.leagues.update_one(
            {"_id": ObjectId(league_id)},
            {"$set": {"minors_spots": 5, "roster_spots": 20}},
        )
        team_id = await seed_team(ctx.db, league_id=league_id)
        gid = await seed_player(ctx.db, name="Yegor Spiridonov", position="G")
        await ctx.db.players.update_one(
            {"_id": ObjectId(gid)},
            {"$set": {
                "player_type": "prospect",
                "primary_position": "G",
                "minor_eligible": True,
            }},
        )
        r = await ctx.client.post(
            f"/api/roster/{team_id}/add",
            json={"player_id": gid},
        )
        assert r.status_code == 200, r.text
        team = await ctx.db.teams.find_one({"_id": ObjectId(team_id)})
        slot = (team.get("lineup") or {}).get(gid)
        assert slot is not None
        assert slot["section"] == "minors"
        assert slot["slot"] == "MIN_G"
