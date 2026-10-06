"""Iter 232N.63 — Minors cap-treatment resolver + integrated cap usage.

Covers:
  1. `apply_minors_treatment` returns full base AAV when player NOT in
     minors, regardless of treatment.
  2. `full` treatment charges 100% of base AAV.
  3. `none` treatment charges 0 for minors.
  4. `default` treatment charges `default_rookie_aav` for minors.
  5. `tiered` charges 50% for prospects (age<24 OR is_prospect=true)
     and 100% for veterans.
  6. `_player_is_in_minors` correctly reads the lineup section.
  7. `_recompute_team_salary_used` applies tiered treatment (integration).
  8. `get_team_cap_used` applies tiered treatment from active contracts.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


# ─────────────────────── Pure resolver tests ────────────────────────


def _mk_player(pid: str, age: int = 30, is_prospect: bool = False):
    return {"_id": pid, "age": age, "is_prospect": is_prospect}


def test_apply_minors_treatment_ignores_players_not_in_minors():
    from utils.cap_treatment import apply_minors_treatment
    p = _mk_player("p1", age=20, is_prospect=True)
    # NOT in minors → treatment doesn't matter, full AAV returned.
    for t in ("full", "none", "default", "tiered"):
        assert apply_minors_treatment(
            p, base_aav=5_000_000, is_in_minors=False, treatment=t,
            default_rookie_aav=800_000,
        ) == 5_000_000


def test_apply_minors_treatment_full():
    from utils.cap_treatment import apply_minors_treatment
    p = _mk_player("p1")
    assert apply_minors_treatment(
        p, base_aav=3_000_000, is_in_minors=True, treatment="full",
    ) == 3_000_000


def test_apply_minors_treatment_none():
    from utils.cap_treatment import apply_minors_treatment
    p = _mk_player("p1")
    assert apply_minors_treatment(
        p, base_aav=3_000_000, is_in_minors=True, treatment="none",
    ) == 0.0


def test_apply_minors_treatment_default():
    from utils.cap_treatment import apply_minors_treatment
    p = _mk_player("p1")
    assert apply_minors_treatment(
        p, base_aav=3_000_000, is_in_minors=True, treatment="default",
        default_rookie_aav=875_000,
    ) == 875_000


def test_apply_minors_treatment_tiered_prospect_50pct():
    from utils.cap_treatment import apply_minors_treatment
    prospect = _mk_player("prospect", age=20)
    vet = _mk_player("vet", age=32)
    is_prospect = _mk_player("flag", age=30, is_prospect=True)

    # Prospect by age → 50%
    assert apply_minors_treatment(
        prospect, base_aav=2_000_000, is_in_minors=True, treatment="tiered",
    ) == 1_000_000
    # Explicit prospect flag → 50% (even if age >= 24)
    assert apply_minors_treatment(
        is_prospect, base_aav=2_000_000, is_in_minors=True, treatment="tiered",
    ) == 1_000_000
    # Veteran → 100%
    assert apply_minors_treatment(
        vet, base_aav=2_000_000, is_in_minors=True, treatment="tiered",
    ) == 2_000_000


def test_player_is_in_minors_reads_lineup_section():
    from utils.cap_treatment import _player_is_in_minors
    lineup = {
        "p1": {"section": "minors", "slot": "MIN"},
        "p2": {"section": "starter", "slot": "C"},
        "p3": {"section": "bench"},
    }
    assert _player_is_in_minors({"_id": "p1"}, lineup) is True
    assert _player_is_in_minors({"_id": "p2"}, lineup) is False
    assert _player_is_in_minors({"_id": "p3"}, lineup) is False
    # Player not in lineup at all
    assert _player_is_in_minors({"_id": "p4"}, lineup) is False


# ─────────────────────── Integration tests ──────────────────────────


async def _seed(db, treatment: str, default_rookie_aav: int = 950_000):
    """Seed a cap-enabled league + 1 team with 3 players (1 prospect in
    minors, 1 veteran in minors, 1 veteran active). Returns ids."""
    admin = ObjectId()
    lg = await db.leagues.insert_one({
        "sport": "nhl", "salary_cap_enabled": True,
        "salary_cap": 90_000_000,
        "minors_cap_treatment": treatment,
        "default_rookie_aav": default_rookie_aav,
        "commissioner_id": str(admin),
        "created_at": datetime.now(timezone.utc),
    })
    league_id = str(lg.inserted_id)

    p_prospect = await db.players.insert_one({
        "name": "N63 Prospect", "position": "LW",
        "nhl_id": f"n63_pro_{ObjectId()}",
        "age": 20, "is_prospect": True,
        "contract": {"aav": 2_000_000},
    })
    p_vet_minor = await db.players.insert_one({
        "name": "N63 Vet Minor", "position": "D",
        "nhl_id": f"n63_vet1_{ObjectId()}",
        "age": 30,
        "contract": {"aav": 4_000_000},
    })
    p_vet_active = await db.players.insert_one({
        "name": "N63 Vet Active", "position": "C",
        "nhl_id": f"n63_vet2_{ObjectId()}",
        "age": 30,
        "contract": {"aav": 6_000_000},
    })

    lineup = {
        str(p_prospect.inserted_id): {"section": "minors", "slot": "MIN"},
        str(p_vet_minor.inserted_id): {"section": "minors", "slot": "MIN"},
        str(p_vet_active.inserted_id): {"section": "starter", "slot": "C"},
    }
    team = await db.teams.insert_one({
        "league_id": league_id, "owner_id": str(admin),
        "name": "N63 Team",
        "roster": [
            str(p_prospect.inserted_id),
            str(p_vet_minor.inserted_id),
            str(p_vet_active.inserted_id),
        ],
        "lineup": lineup,
        "salary_used": 0,
    })
    return {
        "admin": str(admin), "league_id": league_id,
        "team_id": str(team.inserted_id),
        "player_ids": [
            str(p_prospect.inserted_id),
            str(p_vet_minor.inserted_id),
            str(p_vet_active.inserted_id),
        ],
    }


async def _cleanup(db, s):
    from bson import ObjectId as _OID
    await db.leagues.delete_one({"_id": _OID(s["league_id"])})
    await db.teams.delete_one({"_id": _OID(s["team_id"])})
    await db.players.delete_many({
        "_id": {"$in": [_OID(p) for p in s["player_ids"]]},
    })


@pytest.mark.asyncio
async def test_recompute_team_salary_used_tiered_treatment():
    """Prospect in minors → 50% of 2M = 1M. Veteran in minors → 100%
    of 4M = 4M. Active veteran → 100% of 6M = 6M. Total = 11M."""
    from routes import roster as r_mod
    db = _db()
    s = await _seed(db, treatment="tiered")

    # Wire deps
    r_mod._deps["db"] = db

    try:
        used = await r_mod._recompute_team_salary_used(s["team_id"])
        assert used == 11_000_000, f"Expected 11M, got {used:,}"
    finally:
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_recompute_team_salary_used_none_treatment_exempts_minors():
    """Both minors players exempt (0 + 0), only 6M active vet counted."""
    from routes import roster as r_mod
    db = _db()
    s = await _seed(db, treatment="none")
    r_mod._deps["db"] = db
    try:
        used = await r_mod._recompute_team_salary_used(s["team_id"])
        assert used == 6_000_000
    finally:
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_recompute_team_salary_used_default_treatment_uses_rookie_aav():
    """Both minors count as default_rookie_aav ($875k each), vet at
    full 6M. Total = 875k + 875k + 6M = 7_750_000."""
    from routes import roster as r_mod
    db = _db()
    s = await _seed(db, treatment="default", default_rookie_aav=875_000)
    r_mod._deps["db"] = db
    try:
        used = await r_mod._recompute_team_salary_used(s["team_id"])
        assert used == 7_750_000
    finally:
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_recompute_team_salary_used_full_treatment_unchanged():
    """Legacy behaviour: everyone at full AAV. 2M + 4M + 6M = 12M."""
    from routes import roster as r_mod
    db = _db()
    s = await _seed(db, treatment="full")
    r_mod._deps["db"] = db
    try:
        used = await r_mod._recompute_team_salary_used(s["team_id"])
        assert used == 12_000_000
    finally:
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_get_team_cap_used_applies_tiered_via_contracts_path():
    """When active contracts exist, the contract-sum path also honours
    minors_cap_treatment."""
    from routes import contracts as c_mod, roster as r_mod
    db = _db()
    s = await _seed(db, treatment="tiered")

    # Attach real contracts (previous tests used player.contract inline —
    # here we exercise the db.contracts path).
    for pid, aav in zip(
        s["player_ids"], [2_000_000, 4_000_000, 6_000_000],
    ):
        await db.contracts.insert_one({
            "team_id": s["team_id"], "league_id": s["league_id"],
            "player_id": pid, "aav": aav, "status": "active",
        })

    c_mod._deps["db"] = db
    c_mod._deps["_recompute_team_salary_used"] = (
        lambda tid: r_mod._recompute_team_salary_used(tid)
    )

    try:
        used = await c_mod.get_team_cap_used(s["team_id"], s["league_id"])
        # Prospect in minors: 2M * 0.5 = 1M
        # Vet in minors: 4M * 1.0 = 4M (age 30 = not prospect)
        # Vet active: 6M * 1.0 = 6M
        assert used == 11_000_000, f"Expected 11M, got {used:,}"
    finally:
        await db.contracts.delete_many({"team_id": s["team_id"]})
        await _cleanup(db, s)
