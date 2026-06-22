"""Team lineup persistence + compliance.

Endpoints (extracted from server.py iter 109):
  - POST  /teams/{team_id}/lineup
  - GET   /teams/{team_id}/lineup
  - GET   /teams/{team_id}/compliance
  - PUT   /leagues/{league_id}/injury-reserve-compliance-mode

Payloads, auth and runtime behaviour identical to the pre-extraction
implementation. See the full chain of iter-83 (rule enforcement), iter-84
(section caps), iter-85 (lineup warnings), iter-101/102 (roster lock),
iter-104 (emergency budget), iter-105 (per-week + per-season scope) and
iter-107 (emergency eligibility gate) for the historical motivation.
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.post("/teams/{team_id}/lineup")
async def save_team_lineup(team_id: str, payload: dict, request: Request):
    """Persist a team's active-lineup mapping.

    Body: {"lineup": {"<player_id>": {"section": "forward|defense|goalie|bench|ir|minors", "slot": "C|LW|RW|D|G|BN|IR|MIN"}}}

    Sections drive the `% Start` calculation (only forward/defense/goalie count
    as starting). Persisted on the team document so PlayerRoster's existing
    Save Roster button can call this from any client.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_commish = league and (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not (is_owner or is_commish):
        raise HTTPException(status_code=403, detail="Only the team owner or commissioner may edit lineups")

    # ── Iter 101: enforce roster_lock_type / lineup_lock_minutes_before ──
    # Commissioners bypass the lock so they can still adjust lineups during
    # the freeze window (matches existing override semantics for IR/cap gates).
    # ── Iter 105: emergency_changes_* bypass — when enabled and the team has
    # remaining emergency swaps budget, allow the write through and consume a
    # swap from `team.emergency_swaps_used`.
    if league and not is_commish:
        try:
            from utils.lineup_lock import evaluate_lineup_lock
            current_wk = league.get("current_week") or league.get("playoff_start_week")
            lock = evaluate_lineup_lock(league, current_week=current_wk)
            if lock["locked"]:
                emergency_on = bool(league.get("emergency_changes_enabled"))
                in_playoffs = (
                    current_wk is not None
                    and league.get("playoff_start_week") is not None
                    and int(current_wk) >= int(league["playoff_start_week"])
                )
                budget = int(
                    (league.get("emergency_changes_playoffs") or 0) if in_playoffs
                    else (league.get("emergency_changes_regular") or 0)
                )
                scope = league.get("emergency_changes_scope") or "per_week"
                used_field = (
                    f"emergency_swaps_used_{current_wk}"
                    if scope == "per_week" and current_wk
                    else "emergency_swaps_used_season"
                )
                used = int(team.get(used_field) or 0)
                if emergency_on and budget > 0 and used < budget:
                    # ── Iter 107: Validate eligibility BEFORE consuming the swap ──
                    eligibility = set(league.get("emergency_eligibility") or ["any"])
                    if "any" not in eligibility:
                        STARTER_SECTIONS = {"forward", "defense", "goalie"}
                        old_lineup = team.get("lineup") or {}
                        new_lineup = (payload.get("lineup") or {}) if isinstance(payload.get("lineup"), dict) else {}
                        old_starters = {
                            pid for pid, slot in old_lineup.items()
                            if isinstance(slot, dict) and slot.get("section") in STARTER_SECTIONS
                        }
                        new_starters = {
                            pid for pid, slot in new_lineup.items()
                            if isinstance(slot, dict) and slot.get("section") in STARTER_SECTIONS
                        }
                        removed_starters = old_starters - new_starters
                        if removed_starters:
                            _STATUS_MAP = {
                                "scratched": lambda p: (p.get("status") or "").lower() in {"scratched", "healthy_scratch", "hs"},
                                "injured": lambda p: (p.get("status") or "").lower() in {"injured", "ir", "ir-lt", "out", "day-to-day", "dtd"} or bool(p.get("injury_status")),
                                "minors": lambda p: (p.get("status") or "").lower() in {"minors", "ahl", "assigned"} or (p.get("assignment") or "").lower() == "minors",
                                "suspended": lambda p: (p.get("status") or "").lower() in {"suspended", "suspension"},
                                "personal": lambda p: (p.get("status") or "").lower() in {"personal", "personal_leave", "leave"},
                            }
                            allowed_matchers = [_STATUS_MAP[v] for v in eligibility if v in _STATUS_MAP]
                            for pid in removed_starters:
                                try:
                                    player = await db.players.find_one({"_id": ObjectId(pid)})
                                except Exception:
                                    player = None
                                if not player:
                                    continue
                                if not any(m(player) for m in allowed_matchers):
                                    raise HTTPException(
                                        status_code=400,
                                        detail=(
                                            f"Emergency swap denied for {player.get('full_name') or player.get('name') or pid}: "
                                            f"player status doesn't match any allowed criteria "
                                            f"({', '.join(sorted(eligibility))})."
                                        ),
                                    )
                    await db.teams.update_one(
                        {"_id": team["_id"]},
                        {"$inc": {used_field: 1}},
                    )
                    logger.info(
                        f"Emergency roster swap consumed: team={team['_id']} "
                        f"week={current_wk} used={used + 1}/{budget}"
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{lock['reason']} (next unlock: {lock['next_unlock_iso']})"
                        ),
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"lineup_lock evaluation skipped: {e}")

    raw = payload.get("lineup") or {}
    lineup: dict[str, dict] = {}
    valid_sections = {"forward", "defense", "goalie", "bench", "ir", "ir-plus", "taxi", "minors"}
    starting_sections = {"forward", "defense", "goalie"}
    starter_ids: list[str] = []
    section_counts: dict[str, int] = {}
    for pid, info in raw.items():
        if not isinstance(info, dict):
            continue
        section = (info.get("section") or "bench").lower()
        if section not in valid_sections:
            section = "bench"
        slot = info.get("slot") or section.upper()[:3]
        lineup[str(pid)] = {"section": section, "slot": slot}
        section_counts[section] = section_counts.get(section, 0) + 1
        if section in starting_sections:
            starter_ids.append(str(pid))

    # ── Roster-section caps (iter 84) ───────────────────────────
    cap_checks = [
        ("ir", int((league or {}).get("ir_slots") or 0), "IR"),
        ("ir-plus", int((league or {}).get("ir_plus_slots") or 0), "IR+"),
        ("taxi", int((league or {}).get("taxi_squad_size") or 0), "Taxi Squad"),
        ("minors", int((league or {}).get("minors_spots") or 0), "Minors Pool"),
        ("bench", int((league or {}).get("bench_spots") or 0), "Bench"),
    ]
    for section_key, cap, friendly in cap_checks:
        used = section_counts.get(section_key, 0)
        if cap > 0 and used > cap:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{friendly} has {used} player{'s' if used != 1 else ''} but the "
                    f"league only allows {cap}. Move {used - cap} to another section."
                ),
            )
        if cap == 0 and used > 0 and section_key in ("ir", "ir-plus", "taxi", "minors"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{friendly} is disabled for this league (size = 0). "
                    f"Move the {used} player{'s' if used != 1 else ''} you placed "
                    f"there to another section."
                ),
            )

    # ── League rule enforcement (iter 83) ────────────────────────
    from utils.roster_rules import check_min_active_players
    enforce_block = (league or {}).get("allow_illegal_rosters") is False
    active_err = check_min_active_players(league or {}, len(starter_ids))
    if active_err and enforce_block:
        raise HTTPException(status_code=400, detail=active_err)

    warnings: list[dict] = []
    if active_err:
        warnings.append({"code": "min_active_players", "message": active_err})
    min_gp = int((league or {}).get("min_games_played") or 0)
    if min_gp > 0 and starter_ids:
        oids: list = []
        for sid in starter_ids:
            try:
                oids.append(ObjectId(sid))
            except InvalidId:
                pass
        if oids:
            async for p in db.players.find(
                {"_id": {"$in": oids}},
                {"name": 1, "games_played": 1, "stats.games_played": 1},
            ):
                gp = int(p.get("games_played") or (p.get("stats") or {}).get("games_played") or 0)
                if gp < min_gp:
                    warnings.append({
                        "code": "min_games_played",
                        "player_id": str(p["_id"]),
                        "player_name": p.get("name") or "Unknown",
                        "games_played": gp,
                        "required": min_gp,
                        "message": (
                            f"{p.get('name') or 'Player'} has only {gp} GP — "
                            f"below the league's {min_gp} GP minimum."
                        ),
                    })

    # ── Iter 124: log lineup_change activity for the League History
    # transactions feed. We diff old vs new lineup, summarize the moves,
    # and best-effort write an activity row (so a slow write never breaks
    # the save). Owner+commissioner edits are both captured so the
    # commissioner-edit audit trail is visible to all members.
    old_lineup = team.get("lineup") or {}
    moves: list[dict] = []
    for pid, info in lineup.items():
        old_info = old_lineup.get(pid) or {}
        if (old_info.get("section") or "") != info.get("section"):
            try:
                player = await db.players.find_one({"_id": ObjectId(pid)})
            except Exception:
                player = None
            pname = (player or {}).get("full_name") or (player or {}).get("name") or f"Player {pid[:6]}"
            ppos = (player or {}).get("position") or (player or {}).get("primary_position") or ""
            moves.append({
                "player_id": pid,
                "player_name": pname,
                "position": ppos,
                "from": (old_info.get("section") or "bench").upper(),
                "to": info.get("section", "bench").upper(),
            })

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"lineup": lineup, "lineup_updated_at": datetime.now(timezone.utc)}},
    )

    if moves:
        try:
            log_activity = _deps.get("log_activity")
            if log_activity:
                summary_bits = [
                    f"{m['player_name']} ({m['position'] or '—'}) {m['from']} → {m['to']}"
                    for m in moves[:3]
                ]
                more = "" if len(moves) <= 3 else f" + {len(moves) - 3} more"
                message = (
                    f"{team.get('name') or 'Team'} updated lineup: "
                    + ", ".join(summary_bits)
                    + more
                )
                await log_activity(
                    team["league_id"],
                    "lineup_change",
                    message,
                    user["_id"],
                    {
                        "team_id": str(team["_id"]),
                        "team_name": team.get("name"),
                        "moves": moves,
                        "move_count": len(moves),
                        # Surface a representative position so the Transactions
                        # tab's position-filter has something to bite on for
                        # single-player moves. Multi-player moves keep
                        # `moves[]` so the filter can still match any of them.
                        "player_position": moves[0]["position"],
                    },
                )
        except Exception:
            pass

    # Iter 201d — record an IP/UA-stamped lineup_set audit row used by the
    # platform admin's lineup-audit feed + multi-account detection.
    try:
        from routes.admin_platform import record_lineup_event
        # Identify benched top-salary players for tanking detection.
        bench_pids = [
            pid for pid, slot in (lineup or {}).items()
            if isinstance(slot, dict) and slot.get("section") in ("bench", "ir", "minors")
        ]
        await record_lineup_event(
            db, str(team["league_id"]), str(team["_id"]), str(user["_id"]),
            request,
            summary=(
                f"{team.get('name') or 'Team'} lineup saved "
                f"({len(starter_ids)} starters, {len(bench_pids)} benched)"
            ),
            benched_player_ids=bench_pids,
        )
    except Exception:
        pass

    return {
        "team_id": team_id,
        "lineup_size": len(lineup),
        "starter_count": len(starter_ids),
        "saved": True,
        "warnings": warnings,
    }


@router.get("/teams/{team_id}/lineup")
async def get_team_lineup(team_id: str, request: Request):
    db = _deps["db"]
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "lineup": team.get("lineup") or {}}


@router.get("/teams/{team_id}/compliance")
async def get_team_compliance(team_id: str):
    """Return roster compliance status and reasons.

    See iter-83/iter-84 docs for reason codes:
      - roster_size_exceeded, over_salary_cap, healthy_on_ir, minor_ineligible.
    """
    db = _deps["db"]
    _recompute_team_salary_used = _deps["_recompute_team_salary_used"]
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})

    reasons: list[dict] = []
    roster_ids = team.get("roster") or []
    roster_count = len(roster_ids)
    max_roster = int((league or {}).get("roster_spots") or 25)

    if roster_count > max_roster:
        reasons.append({
            "code": "too_many_players",
            "label": "Too many players on the roster",
            "detail": f"{roster_count} on roster vs limit {max_roster}",
        })

    salary_used = float(team.get("salary_used") or 0.0)
    salary_cap = (league or {}).get("salary_cap")
    if (league or {}).get("salary_cap_enabled") and salary_cap:
        try:
            salary_used = await _recompute_team_salary_used(team_id)
        except Exception:
            pass
    if (league or {}).get("salary_cap_enabled") and salary_cap and salary_used > salary_cap:
        reasons.append({
            "code": "over_salary_cap",
            "label": "Over the salary cap",
            "detail": f"${salary_used:,.0f} used vs ${salary_cap:,.0f} cap",
        })

    lineup = team.get("lineup") or {}
    if lineup and roster_ids:
        try:
            obj_ids = [ObjectId(pid) for pid in roster_ids]
        except Exception:
            obj_ids = []
        players = await db.players.find(
            {"_id": {"$in": obj_ids}},
            {"name": 1, "position": 1, "games_played": 1, "birth_date": 1,
             "injury_status": 1, "injury_type": 1, "status": 1},
        ).to_list(200)
        max_age = int((league or {}).get("minors_max_age") or 22)
        max_games = int((league or {}).get("minors_max_career_games") or 25)

        def _age_of(p):
            bd = p.get("birth_date")
            if not bd:
                return None
            try:
                bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
                return (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
            except Exception:
                return None

        for p in players:
            pid = str(p["_id"])
            slot_info = lineup.get(pid)
            if not slot_info:
                continue
            section = (slot_info.get("section") or "").lower()
            if section == "ir":
                injury = (p.get("injury_status") or p.get("status") or "").lower()
                if not injury or injury in ("healthy", "active", "ok"):
                    reasons.append({
                        "code": "healthy_on_ir",
                        "label": "Healthy player on IR",
                        "detail": f"{p.get('name')} is on IR but has no injury status",
                        "player_id": pid,
                        "player_name": p.get("name"),
                    })
            elif section == "minors":
                gp = int(p.get("games_played") or 0)
                age = _age_of(p)
                eligible = (gp <= max_games) or (age is not None and age <= max_age)
                if not eligible:
                    reasons.append({
                        "code": "minor_ineligible",
                        "label": "Minor league player ineligible to be on minors",
                        "detail": f"{p.get('name')} ({age}y, {gp} GP) exceeds league minors caps ({max_age}y / {max_games} GP)",
                        "player_id": pid,
                        "player_name": p.get("name"),
                    })

    compliant = len(reasons) == 0

    retentions_list = team.get("salary_retentions") or []
    retention_slots_total = int((league or {}).get("salary_retention_slots") or 3)
    retention_slots_used = len(retentions_list)
    retained_salary_total = sum(float(r.get("amount") or 0.0) for r in retentions_list)

    return {
        "team_id": team_id,
        "compliant": compliant,
        "reasons": reasons,
        "roster_count": roster_count,
        "max_roster": max_roster,
        "salary_used": salary_used,
        "salary_cap": salary_cap,
        "salary_cap_enabled": bool((league or {}).get("salary_cap_enabled")),
        "salary_retention_slots_total": retention_slots_total,
        "salary_retention_slots_used": retention_slots_used,
        "salary_retention_slots_remaining": max(0, retention_slots_total - retention_slots_used),
        "retained_salary_total": retained_salary_total,
        "injury_reserve_compliance_mode": (league or {}).get("injury_reserve_compliance_mode") or "none",
    }


@router.put("/leagues/{league_id}/injury-reserve-compliance-mode")
async def set_injury_reserve_compliance_mode(league_id: str, payload: dict, request: Request):
    """Commissioner-only setter for league-wide IR compliance enforcement.

    Mode values:
      none, lock_all, lock_waivers, lock_adds, lock_adds_trades,
      illegal_roster, drop_player
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("commissioner_id") != user["_id"] and user["_id"] not in (league.get("co_commissioners") or []):
        raise HTTPException(status_code=403, detail="Only the commissioner may change this setting")

    mode = (payload.get("mode") or "none").lower()
    valid = {"none", "lock_all", "lock_waivers", "lock_adds",
             "lock_adds_trades", "illegal_roster", "drop_player"}
    if mode not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Valid: {sorted(valid)}")
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"injury_reserve_compliance_mode": mode}},
    )
    return {"league_id": league_id, "injury_reserve_compliance_mode": mode}
