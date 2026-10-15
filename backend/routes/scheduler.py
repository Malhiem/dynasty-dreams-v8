"""Authenticated combined scheduler: inspect, check, preview, then atomically apply."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.combined_scheduler import Settings, check, defaults, solve
from services.schedule_store import apply_preview, context, preview_document, season

router = APIRouter()
_deps = {}
_solvers = asyncio.Semaphore(2)


def setup(deps):
    _deps.update(deps)


async def authorized(request, league_id):
    user = await _deps["get_current_user"](request)
    return user, await context(_deps["db"], league_id, user)


def calendar_errors(league, settings):
    from routes.matchups import _season_schedule_warnings
    errors, _ = _season_schedule_warnings(season_start=league.get("season_start_date"), season_end=league.get("season_end_date"),
        matchup_length_days=int(league.get("matchup_length_days") or 7), num_weeks=settings.weeks)
    start = int(league.get("playoff_start_week") or settings.weeks + 1)
    if league.get("playoffs_enabled", True) and start <= settings.weeks:
        errors.append("Regular-season weeks overlap the configured playoff start. Update the playoff dates first.")
    return errors


@router.get("/leagues/{league_id}/schedule/rules")
async def get_rules(league_id: str, request: Request):
    _, ctx = await authorized(request, league_id)
    db = _deps["db"]
    hello = await db.command("hello")
    return {"settings": defaults(ctx["league"], ctx["teams"]).model_dump(), "season": season(ctx["league"]),
            "team_count": len(ctx["teams"]), "locked_games": len(ctx["locked"]), "version": int(ctx["league"].get("schedule_version") or 0),
            "can_apply": bool(hello.get("setName") or hello.get("msg") == "isdbgrid")}


@router.post("/leagues/{league_id}/schedule/check")
async def check_rules(league_id: str, settings: Settings, request: Request):
    _, ctx = await authorized(request, league_id)
    errors = check(ctx["teams"], settings, ctx["locked"]) + calendar_errors(ctx["league"], settings)
    return {"status": "infeasible" if errors else "ready", "errors": errors,
            "message": "Basic checks passed; generate a preview to verify a complete weekly arrangement." if not errors else "Resolve these conflicts before generating."}


async def make_preview(db, league_id, user, ctx, settings):
    errors = calendar_errors(ctx["league"], settings)
    if errors: return {"status": "infeasible", "errors": errors}
    try:
        await asyncio.wait_for(_solvers.acquire(), timeout=1)
    except TimeoutError: raise HTTPException(429, "Other schedules are being generated. Try again shortly.")
    try:
        solved = await run_in_threadpool(solve, ctx["teams"], settings, ctx["locked"])
    except ImportError as exc:
        raise HTTPException(503, "The schedule solver is not installed on this server.") from exc
    finally: _solvers.release()
    if solved["status"] != "feasible": return solved
    solved["preview_id"] = await preview_document(db, league_id, user, ctx, settings, solved)
    solved["season"] = season(ctx["league"])
    return solved


@router.post("/leagues/{league_id}/schedule/preview")
async def preview_schedule(league_id: str, settings: Settings, request: Request):
    user, ctx = await authorized(request, league_id)
    return await make_preview(_deps["db"], league_id, user, ctx, settings)


class Apply(BaseModel):
    preview_id: str = Field(min_length=24, max_length=24)


@router.post("/leagues/{league_id}/schedule/apply")
async def apply_schedule(league_id: str, payload: Apply, request: Request):
    user, _ = await authorized(request, league_id)
    return await apply_preview(_deps["db"], league_id, payload.preview_id, user)
