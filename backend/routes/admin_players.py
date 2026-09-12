"""Iter 232N.64/65 — Admin Player DB router.

Gives platform admins full-CRUD visibility into the ~3,300 player DB
so they can:
  • Search / filter / paginate every player.
  • Fix inaccurate rows (position, age, is_prospect, contract, cap_hit,
    team, league, name, stats).
  • Add missing minor leaguers that aren't in the source feed.
  • Delete stale rows (guarded — only players with zero roster
    references).
  • Refresh the DB from one of three sources:
      - `reseed`  — re-runs the NHL bulk upsert (existing seed_nhl_data)
      - `nhl_api` — 232N.65: real concurrent fetch of every NHL roster +
                     prospect list, with dry-run diff and selective apply
      - `csv`     — multipart upload with a two-step preview → commit
                     flow, so bad rows are caught before hitting Mongo
  • Bulk-act on filtered sets (mark_prospect, unmark_prospect, delete).

Every write hits `player_admin_audit` so admins can see who changed
what across all leagues + the platform.
"""
from __future__ import annotations

import csv
import io
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services import nhl_sync

router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)

# ─── In-process token cache for dry-run + CSV preview ──────────────
# Small, ephemeral (10-minute expiry), admin-scoped. Cheaper than a
# Mongo TTL collection for something we hit once per sync UI open.
_TOKEN_TTL_SEC = 600
_sync_previews: dict[str, dict] = {}
_csv_previews: dict[str, dict] = {}


def _gc_tokens(bucket: dict) -> None:
    now = time.time()
    stale = [k for k, v in bucket.items() if v.get("_expires_at", 0) < now]
    for k in stale:
        bucket.pop(k, None)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


async def _require_admin(request: Request):
    user = await _get_user(request)
    if (
        not user
        or (user.get("role") != "admin"
            and user.get("permission_tier") not in ("admin", "senior_admin"))
    ):
        raise HTTPException(status_code=403, detail="Platform admin only")
    return user


# ─── Editable field allow-list ─────────────────────────────────────
# Full CRUD per user pick. Only these fields are accepted on
# create/update to prevent accidental writes to computed/audit fields
# like `seeded_at`, `nhl_data_synced_at`, `last_synced_at`, etc.
_EDITABLE_FIELDS = {
    "name", "position", "player_type", "team", "team_name", "league",
    "age", "birth_date", "birth_country", "shoots", "nhl_id",
    "games_played", "goals", "assists", "points", "shots",
    "plus_minus", "penalty_minutes",
    "power_play_goals", "power_play_points",
    "short_handed_goals", "short_handed_points",
    "even_strength_goals", "even_strength_points",
    "overtime_goals", "game_winning_goals",
    "shooting_pct", "faceoff_win_pct", "toi_per_game",
    "season",
    # Cap / eligibility
    "cap_hit", "salary", "is_prospect", "contract",
    "headshot_url",
}

# Fields we sync from the NHL API on `apply` (subset of EDITABLE). We
# never overwrite cap/contract from the feed — that's league-side data.
_NHL_SYNC_FIELDS = (
    "name", "position", "team", "league", "age",
    "birth_date", "birth_country", "shoots", "is_prospect",
    "headshot_url",
)

# Positions we accept in CSV validation. Matches the modal `Select`.
_VALID_POSITIONS = {"C", "LW", "RW", "D", "G"}


def _sanitize(payload: dict) -> dict:
    """Keep only allow-listed fields."""
    return {k: v for k, v in (payload or {}).items() if k in _EDITABLE_FIELDS}


# ─── Audit trail helper ────────────────────────────────────────────

async def _audit(db, actor: dict, action: str, player_id: str,
                 before: dict | None, after: dict | None,
                 note: str | None = None):
    await db.player_admin_audit.insert_one({
        "actor_id": str(actor.get("_id")),
        "actor_email": actor.get("email"),
        "actor_role": actor.get("role") or "user",
        "action": action,           # "create" | "update" | "delete" | "refresh" | "bulk"
        "player_id": player_id,     # or "*" for bulk/refresh
        "before": before,
        "after": after,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(),
    })


# ─── List / search ─────────────────────────────────────────────────


@router.get("/admin/players")
async def admin_list_players(
    request: Request,
    q: Optional[str] = None,
    position: Optional[str] = None,
    league: Optional[str] = None,
    is_prospect: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
):
    """Iter 232N.64 — Paginated + searchable player DB view."""
    await _require_admin(request)
    db = _db()
    skip = max(0, int(skip))
    limit = max(1, min(int(limit), 200))

    filt: dict = {}
    if q:
        filt["name"] = {"$regex": q, "$options": "i"}
    if position:
        filt["position"] = position
    if league:
        filt["league"] = league
    if is_prospect is not None:
        filt["is_prospect"] = bool(is_prospect)

    total = await db.players.count_documents(filt)
    rows = await db.players.find(filt).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    for r in rows:
        r["id"] = str(r.pop("_id"))
    return {"total": total, "skip": skip, "limit": limit, "players": rows}


# ─── Create ────────────────────────────────────────────────────────


class CreatePlayerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    position: Optional[str] = None
    player_type: Optional[str] = None
    team: Optional[str] = None
    team_name: Optional[str] = None
    league: Optional[str] = "NHL"
    age: Optional[int] = Field(None, ge=15, le=60)
    nhl_id: Optional[str] = None
    is_prospect: Optional[bool] = False
    cap_hit: Optional[int] = None
    contract: Optional[dict] = None


@router.post("/admin/players")
async def admin_create_player(input: CreatePlayerRequest, request: Request):
    admin = await _require_admin(request)
    db = _db()
    doc = _sanitize(input.model_dump(exclude_none=True))
    if not doc.get("nhl_id"):
        doc["nhl_id"] = f"admin_{ObjectId()}"
    doc["seeded_at"] = datetime.now(timezone.utc)
    doc["created_by_admin_id"] = str(admin["_id"])
    r = await db.players.insert_one(doc)
    doc["id"] = str(r.inserted_id)
    doc.pop("_id", None)
    await _audit(db, admin, "create", str(r.inserted_id), None, doc)
    return doc


# ─── Update ────────────────────────────────────────────────────────


@router.put("/admin/players/{player_id}")
async def admin_update_player(player_id: str, payload: dict, request: Request):
    admin = await _require_admin(request)
    db = _db()
    try:
        before = await db.players.find_one({"_id": ObjectId(player_id)})
    except Exception:
        before = None
    if not before:
        raise HTTPException(status_code=404, detail="Player not found")

    updates = _sanitize(payload)
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields provided")

    await db.players.update_one({"_id": ObjectId(player_id)}, {"$set": updates})
    after = await db.players.find_one({"_id": ObjectId(player_id)})
    after["id"] = str(after.pop("_id"))
    before["id"] = str(before.pop("_id"))
    await _audit(db, admin, "update", player_id, before, {k: after[k] for k in updates if k in after})
    return after


# ─── Delete ────────────────────────────────────────────────────────


@router.delete("/admin/players/{player_id}")
async def admin_delete_player(player_id: str, request: Request):
    admin = await _require_admin(request)
    db = _db()
    on_roster = await db.teams.count_documents({"roster": player_id})
    if on_roster > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Player is on {on_roster} active roster(s). Remove from all rosters first.",
        )
    try:
        before = await db.players.find_one({"_id": ObjectId(player_id)})
    except Exception:
        before = None
    if not before:
        raise HTTPException(status_code=404, detail="Player not found")
    await db.players.delete_one({"_id": ObjectId(player_id)})
    before["id"] = str(before.pop("_id"))
    await _audit(db, admin, "delete", player_id, before, None)
    return {"ok": True, "deleted": player_id}


# ─── Audit trail ───────────────────────────────────────────────────


@router.get("/admin/players/audit")
async def admin_player_audit(request: Request, limit: int = 100):
    await _require_admin(request)
    db = _db()
    limit = max(1, min(int(limit), 500))
    rows = await db.player_admin_audit.find().sort("at", -1).limit(limit).to_list(limit)
    for r in rows:
        r["id"] = str(r.pop("_id"))
    return {"rows": rows, "count": len(rows)}


# ─── Refresh actions ───────────────────────────────────────────────


class RefreshRequest(BaseModel):
    source: str = Field(..., pattern=r"^(reseed|nhl_api|csv)$")
    note: Optional[str] = None


@router.post("/admin/players/refresh")
async def admin_refresh_players(input: RefreshRequest, request: Request):
    """Iter 232N.64 — Kick off a `reseed` (subprocess) refresh. NHL API
    dry-run/apply lives in the dedicated `/sync` endpoints below."""
    admin = await _require_admin(request)
    db = _db()
    if input.source == "csv":
        raise HTTPException(
            status_code=400,
            detail="Use POST /admin/players/csv/preview then /commit for CSV imports (multipart upload).",
        )
    if input.source == "nhl_api":
        raise HTTPException(
            status_code=400,
            detail="Use POST /admin/players/sync?dry_run=true then /sync/apply for NHL API imports.",
        )

    started_at = datetime.now(timezone.utc)
    upserted = 0
    error: Optional[str] = None

    if input.source == "reseed":
        try:
            import subprocess
            proc = subprocess.run(
                ["python", "/app/backend/seed_nhl_data.py"],
                capture_output=True, text=True, timeout=110,
            )
            if proc.returncode != 0:
                error = (proc.stderr or "seed failed").strip()[-500:]
            else:
                touched_after = await db.players.count_documents({
                    "nhl_data_synced_at": {"$gte": started_at.isoformat()},
                })
                upserted = touched_after
        except Exception as e:
            error = str(e)[-500:]

    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    entry = {
        "source": input.source, "started_at": started_at.isoformat(),
        "duration_ms": duration_ms, "upserted": upserted,
        "error": error, "note": input.note,
    }
    await _audit(db, admin, "refresh", "*", None, entry, note=input.note)
    return {"ok": error is None, **entry}


# ─── Iter 232N.65: NHL API dry-run + selective apply ───────────────


class SyncRequest(BaseModel):
    dry_run: bool = True
    team_codes: Optional[list[str]] = None    # None → all 32 NHL teams
    note: Optional[str] = None


@router.post("/admin/players/sync")
async def admin_sync_from_nhl(input: SyncRequest, request: Request):
    """Fetch the current NHL rosters + prospect pool and compute a
    diff against `db.players`.

    When `dry_run=true` (default) we return the diff + a `sync_token`
    that the client passes back to `/sync/apply` with the row keys they
    want to accept. Nothing is written to Mongo in this call.

    When `dry_run=false` we skip the token round-trip and apply
    everything except `removed` (which is always opt-in — we don't want
    a slow feed to nuke real players).
    """
    admin = await _require_admin(request)
    db = _db()
    started_at = datetime.now(timezone.utc)

    candidates, fetch_errors = await nhl_sync.fetch_all_players(input.team_codes)
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail=f"NHL API unreachable — no players fetched. Errors: {fetch_errors[:3]}",
        )

    existing_cursor = db.players.find(
        {}, {"nhl_id": 1, "name": 1, "team": 1, "age": 1,
             "position": 1, "is_prospect": 1, "birth_date": 1,
             "league": 1},
    )
    existing = await existing_cursor.to_list(length=None)
    diff = nhl_sync.build_diff(existing, candidates)

    if input.dry_run:
        _gc_tokens(_sync_previews)
        token = uuid.uuid4().hex
        _sync_previews[token] = {
            "admin_id": str(admin.get("_id")),
            "diff": diff,
            "candidates_by_id": {c["nhl_id"]: c for c in candidates},
            "started_at": started_at.isoformat(),
            "note": input.note,
            "_expires_at": time.time() + _TOKEN_TTL_SEC,
        }
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        return {
            "ok": True,
            "dry_run": True,
            "sync_token": token,
            "expires_in_sec": _TOKEN_TTL_SEC,
            "duration_ms": duration_ms,
            "fetch_errors": fetch_errors,
            "diff": diff,
        }

    # Non-dry-run: apply everything except `removed`.
    result = await _apply_diff(db, admin, diff,
                               {c["nhl_id"]: c for c in candidates},
                               apply_all=True, apply_removed=False,
                               note=input.note, started_at=started_at)
    return {"ok": True, "dry_run": False, "fetch_errors": fetch_errors, **result}


class SyncApplyRequest(BaseModel):
    sync_token: str
    apply_new: list[str] = Field(default_factory=list)          # nhl_ids
    apply_age: list[str] = Field(default_factory=list)
    apply_team: list[str] = Field(default_factory=list)
    apply_position: list[str] = Field(default_factory=list)
    apply_prospect: list[str] = Field(default_factory=list)
    apply_duplicates: list[str] = Field(default_factory=list)   # stale ids to merge/drop
    apply_removed: list[str] = Field(default_factory=list)      # explicit opt-in
    note: Optional[str] = None


@router.post("/admin/players/sync/apply")
async def admin_sync_apply(input: SyncApplyRequest, request: Request):
    """Commit a selective set of rows from a prior dry-run to Mongo."""
    admin = await _require_admin(request)
    db = _db()
    _gc_tokens(_sync_previews)
    cached = _sync_previews.get(input.sync_token)
    if not cached:
        raise HTTPException(
            status_code=410,
            detail="Sync token expired or unknown — please re-run the dry run.",
        )
    if cached["admin_id"] != str(admin.get("_id")):
        raise HTTPException(status_code=403, detail="Token belongs to a different admin")

    started_at = datetime.now(timezone.utc)
    diff = cached["diff"]
    candidates_by_id = cached["candidates_by_id"]

    # Build a filtered diff scoped to the caller's picks.
    selected_new_ids = set(input.apply_new)
    selected_age_ids = set(input.apply_age)
    selected_team_ids = set(input.apply_team)
    selected_pos_ids = set(input.apply_position)
    selected_prosp_ids = set(input.apply_prospect)
    selected_dup_stale_ids = set(input.apply_duplicates)
    selected_removed_ids = set(input.apply_removed)

    filt_diff = {
        "new_players":       [c for c in diff["new_players"]      if c["nhl_id"] in selected_new_ids],
        "age_changes":       [r for r in diff["age_changes"]      if r["nhl_id"] in selected_age_ids],
        "team_changes":      [r for r in diff["team_changes"]     if r["nhl_id"] in selected_team_ids],
        "position_changes":  [r for r in diff["position_changes"] if r["nhl_id"] in selected_pos_ids],
        "prospect_changes":  [r for r in diff["prospect_changes"] if r["nhl_id"] in selected_prosp_ids],
        "duplicates":        [d for d in diff.get("duplicates", []) if d["stale_id"] in selected_dup_stale_ids],
        "removed":           [r for r in diff["removed"]          if r["nhl_id"] in selected_removed_ids],
    }

    result = await _apply_diff(
        db, admin, filt_diff, candidates_by_id,
        apply_all=True, apply_removed=True,     # `filt_diff.removed` is already user-filtered
        note=input.note, started_at=started_at,
    )
    # Consume the token — one apply per dry run.
    _sync_previews.pop(input.sync_token, None)
    return {"ok": True, **result}


async def _apply_diff(db, admin, diff, candidates_by_id,
                      apply_all: bool, apply_removed: bool,
                      note: Optional[str], started_at):
    """Shared write path used by both `POST /sync (dry_run=false)` and
    `POST /sync/apply`. Handles every bucket + audits totals."""
    inserted = 0
    deleted = 0
    sync_iso = started_at.isoformat()

    for c in diff.get("new_players", []):
        raw = candidates_by_id.get(c["nhl_id"], c)
        doc = {k: raw.get(k) for k in _NHL_SYNC_FIELDS if raw.get(k) is not None}
        doc["nhl_id"] = c["nhl_id"]
        doc["seeded_at"] = started_at
        doc["nhl_data_synced_at"] = sync_iso
        try:
            await db.players.insert_one(doc)
            inserted += 1
        except Exception as e:
            logger.info("sync insert skipped for %s: %s", c["nhl_id"], str(e)[-120:])

    async def _apply_field(rows, field, source_key):
        n = 0
        for r in rows:
            if source_key not in r:
                continue
            try:
                res = await db.players.update_one(
                    {"_id": ObjectId(r["existing_id"])},
                    {"$set": {field: r[source_key],
                              "nhl_data_synced_at": sync_iso}},
                )
                if res.modified_count or res.matched_count:
                    n += 1
            except Exception:
                continue
        return n

    updated_age       = await _apply_field(diff.get("age_changes", []),      "age",         "new_age")
    updated_team      = await _apply_field(diff.get("team_changes", []),     "team",        "new_team")
    updated_position  = await _apply_field(diff.get("position_changes", []), "position",    "new_position")
    updated_prospect  = await _apply_field(diff.get("prospect_changes", []), "is_prospect", "new_is_prospect")

    if apply_removed:
        for r in diff.get("removed", []):
            try:
                on_roster = await db.teams.count_documents({"roster": r["existing_id"]})
                if on_roster > 0:
                    continue  # never nuke someone actively rostered
                await db.players.delete_one({"_id": ObjectId(r["existing_id"])})
                deleted += 1
            except Exception:
                continue

    # Duplicate merges: drop the stale row (roster-safe). The fresh row
    # is already handled via the `new_players` bucket if the caller
    # opted into that.
    dup_merged = 0
    dup_skipped_on_roster = 0
    for d in diff.get("duplicates", []):
        stale_id = d.get("stale_id")
        if not stale_id:
            continue
        try:
            on_roster = await db.teams.count_documents({"roster": stale_id})
            if on_roster > 0:
                dup_skipped_on_roster += 1
                continue
            await db.players.delete_one({"_id": ObjectId(stale_id)})
            dup_merged += 1
        except Exception:
            continue

    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    entry = {
        "source": "nhl_api",
        "started_at": started_at.isoformat(),
        "duration_ms": duration_ms,
        "inserted": inserted,
        "updated_age": updated_age,
        "updated_team": updated_team,
        "updated_position": updated_position,
        "updated_prospect": updated_prospect,
        "duplicates_merged": dup_merged,
        "duplicates_skipped_on_roster": dup_skipped_on_roster,
        "deleted": deleted,
        "note": note,
    }
    await _audit(db, admin, "refresh", "*", None, entry, note=note)
    return entry


# ─── Iter 232N.65: CSV validation preview → commit ─────────────────


def _validate_csv_row(idx: int, row: dict) -> tuple[dict, list[str]]:
    """Return (cleaned_row, errors_for_this_row). We tolerate empty
    cells and skip them; missing identity fields are an error.

    Iter 232N.77 — Comment rows starting with `#` (the template's
    inline validation hint) are treated as skippable and produce no
    errors so downloading the template + saving unmodified doesn't
    trip validation."""
    # Detect a comment row: the CSV parser gives us a `{first_col: "# ..."}`
    # style dict; we sniff any non-empty value starting with "#" to be safe.
    for v in row.values():
        if isinstance(v, str) and v.strip().startswith("#"):
            return {}, ["__comment_row__"]

    errors: list[str] = []
    clean = _sanitize({k: v for k, v in row.items() if v not in ("", None)})

    if not clean.get("nhl_id") and not (clean.get("name") and clean.get("team")):
        errors.append("row must have nhl_id OR (name + team)")

    if "position" in clean and clean["position"] not in _VALID_POSITIONS:
        errors.append(f"invalid position '{clean['position']}' (valid: {sorted(_VALID_POSITIONS)})")

    for numeric in ("age", "cap_hit", "salary", "goals", "assists", "points",
                    "games_played"):
        if numeric in clean:
            try:
                clean[numeric] = int(float(clean[numeric]))
            except (TypeError, ValueError):
                errors.append(f"'{numeric}' must be numeric (got '{clean[numeric]}')")

    if "age" in clean and isinstance(clean["age"], int) and not (15 <= clean["age"] <= 60):
        errors.append(f"age {clean['age']} out of range (15-60)")

    if "is_prospect" in clean:
        v = str(clean["is_prospect"]).strip().lower()
        if v in ("true", "1", "yes", "y"):
            clean["is_prospect"] = True
        elif v in ("false", "0", "no", "n"):
            clean["is_prospect"] = False
        else:
            errors.append(f"'is_prospect' must be true/false (got '{clean['is_prospect']}')")

    return clean, errors


@router.get("/admin/players/csv/template")
async def admin_csv_template(request: Request):
    """Iter 232N.77 — Downloadable CSV template for bulk cap imports.

    Returns a UTF-8 CSV file with:
      • The exact column headers the /csv/preview endpoint accepts
        (subset of `_EDITABLE_FIELDS` focused on cap + identity).
      • A commented `# Row must have either an nhl_id OR (name + team).`
        line explaining validation.
      • Three example rows (one full veteran, one prospect, one
        admin-added minor leaguer) so the shape is obvious.

    The CSV can be filled in Excel / Google Sheets and re-uploaded via
    the Player DB panel's CSV preview button — the same two-step
    preview → commit flow validates every row before it hits Mongo.
    """
    await _require_admin(request)
    # Column order below is intentional: identity keys first, then
    # position/team, then cap/contract, then optional stats. Admins
    # typically fill the first block for prospects and the whole row
    # for veterans.
    headers = [
        "nhl_id", "name", "position", "team", "team_name", "league",
        "age", "birth_date", "birth_country", "shoots",
        "is_prospect",
        "cap_hit", "salary",
        "games_played", "goals", "assists", "points",
        "shooting_pct", "toi_per_game", "season",
    ]
    rows = [
        headers,
        # Comment row — the CSV parser skips rows whose first cell
        # starts with "#", so this survives the round-trip and gives
        # the admin an inline reminder of the identity rule.
        [
            "# Row must have either an nhl_id OR (name + team). "
            "position ∈ {C,LW,RW,D,G}. age ∈ [15,60]. "
            "is_prospect ∈ {true,false}. cap_hit + salary are integer dollars.",
        ],
        # Example 1 — full veteran row (Auston Matthews).
        [
            "8479318", "Auston Matthews", "C", "TOR", "Toronto Maple Leafs",
            "NHL", "27", "1997-09-17", "USA", "L",
            "false",
            "13250000", "13250000",
            "82", "60", "45", "105",
            "18.5", "20.3", "2025-26",
        ],
        # Example 2 — prospect row (junior leaguer, cap TBD).
        [
            "8484144", "Connor Bedard", "C", "CHI", "Chicago Blackhawks",
            "NHL", "20", "2005-07-17", "CAN", "R",
            "false",
            "950000", "950000",
            "68", "22", "39", "61",
            "10.2", "20.1", "2025-26",
        ],
        # Example 3 — admin-added minor leaguer without an nhl_id.
        # `nhl_id` blank → the importer stamps `admin_<oid>` on insert.
        [
            "", "Placeholder Prospect", "LW", "TOR", "Toronto Marlies",
            "AHL", "22", "2003-04-11", "CAN", "L",
            "true",
            "", "",
            "", "", "", "",
            "", "", "2025-26",
        ],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="player_db_cap_import_template.csv"',
        },
    )


@router.post("/admin/players/csv/preview")
async def admin_csv_preview(
    request: Request,
    file: UploadFile = File(...),
    note: Optional[str] = None,
):
    """Parse + validate an uploaded CSV *without* touching Mongo.

    Returns a preview table (up to 500 rows) with per-row errors + a
    `preview_token` the caller passes to `/csv/commit` to actually
    upsert the accepted rows.
    """
    admin = await _require_admin(request)
    raw = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    rows_preview: list[dict] = []
    cleaned_rows: list[dict] = []
    total_read = 0
    total_valid = 0
    total_errors = 0

    for i, row in enumerate(reader):
        total_read += 1
        if i >= 5000:
            break
        clean, errors = _validate_csv_row(i, row)
        # Iter 232N.77 — Skip inline "# ..." template comment rows.
        if errors == ["__comment_row__"]:
            total_read -= 1
            continue
        valid = not errors
        if valid:
            total_valid += 1
        else:
            total_errors += 1
        if i < 500:  # only include first 500 in preview table
            rows_preview.append({
                "index": i,
                "raw_name": row.get("name") or clean.get("name"),
                "raw_team": row.get("team") or clean.get("team"),
                "raw_position": row.get("position") or clean.get("position"),
                "raw_age": row.get("age") or clean.get("age"),
                "clean": clean,
                "errors": errors,
                "valid": valid,
            })
        cleaned_rows.append({"index": i, "clean": clean, "errors": errors, "valid": valid})

    _gc_tokens(_csv_previews)
    token = uuid.uuid4().hex
    _csv_previews[token] = {
        "admin_id": str(admin.get("_id")),
        "rows": cleaned_rows,      # full set, not just first 500
        "note": note,
        "_expires_at": time.time() + _TOKEN_TTL_SEC,
    }

    return {
        "ok": True,
        "preview_token": token,
        "expires_in_sec": _TOKEN_TTL_SEC,
        "totals": {
            "read": total_read,
            "valid": total_valid,
            "errors": total_errors,
        },
        "rows": rows_preview,
        "truncated_preview": total_read > 500,
        "row_cap_reached": total_read >= 5000,
    }


class CsvCommitRequest(BaseModel):
    preview_token: str
    apply_indices: Optional[list[int]] = None   # None → all valid rows
    note: Optional[str] = None


@router.post("/admin/players/csv/commit")
async def admin_csv_commit(input: CsvCommitRequest, request: Request):
    """Upsert the rows selected from a prior CSV preview by `nhl_id`
    (fallback `name + team`)."""
    admin = await _require_admin(request)
    db = _db()
    _gc_tokens(_csv_previews)
    cached = _csv_previews.get(input.preview_token)
    if not cached:
        raise HTTPException(
            status_code=410,
            detail="Preview token expired or unknown — re-upload the CSV.",
        )
    if cached["admin_id"] != str(admin.get("_id")):
        raise HTTPException(status_code=403, detail="Token belongs to a different admin")

    started_at = datetime.now(timezone.utc)
    upserted = 0
    skipped_invalid = 0
    write_errors: list[str] = []
    apply_set = set(input.apply_indices) if input.apply_indices is not None else None

    for row in cached["rows"]:
        if apply_set is not None and row["index"] not in apply_set:
            continue
        if not row["valid"]:
            skipped_invalid += 1
            continue
        clean = row["clean"]
        nhl_id = clean.get("nhl_id")
        if nhl_id:
            query: dict = {"nhl_id": str(nhl_id)}
        else:
            query = {"name": clean["name"], "team": clean["team"]}
        try:
            await db.players.update_one(
                query,
                {"$set": clean, "$setOnInsert": {"seeded_at": started_at}},
                upsert=True,
            )
            upserted += 1
        except Exception as e:
            write_errors.append(f"Row {row['index']}: {str(e)[-160:]}")

    _csv_previews.pop(input.preview_token, None)

    entry = {
        "source": "csv", "started_at": started_at.isoformat(),
        "upserted": upserted,
        "skipped_invalid": skipped_invalid,
        "errors": write_errors[:20],
        "note": input.note or cached.get("note"),
    }
    await _audit(db, admin, "refresh", "*", None, entry, note=entry["note"])
    return {"ok": True, **entry}


# ── Backwards-compat: old CSV endpoint now runs preview+commit in one
#    shot so existing clients keep working. New UI uses the two-step
#    flow above.
@router.post("/admin/players/refresh/csv")
async def admin_refresh_players_csv(
    request: Request,
    file: UploadFile = File(...),
    note: Optional[str] = None,
):
    admin = await _require_admin(request)
    db = _db()
    started_at = datetime.now(timezone.utc)
    raw = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    upserted = 0
    errors: list[str] = []
    for i, row in enumerate(reader):
        if i > 5000:
            errors.append("Row cap 5000 reached — split large imports.")
            break
        clean, row_errors = _validate_csv_row(i, row)
        # Iter 232N.77 — Skip inline "# ..." template comment rows.
        if row_errors == ["__comment_row__"]:
            continue
        if row_errors:
            errors.append(f"Row {i}: {row_errors[0]}")
            continue
        nhl_id = clean.get("nhl_id")
        query = {"nhl_id": str(nhl_id)} if nhl_id else {"name": clean["name"], "team": clean["team"]}
        try:
            await db.players.update_one(
                query,
                {"$set": clean, "$setOnInsert": {"seeded_at": started_at}},
                upsert=True,
            )
            upserted += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)[-160:]}")

    entry = {
        "source": "csv", "started_at": started_at.isoformat(),
        "upserted": upserted, "errors": errors[:20], "note": note,
    }
    await _audit(db, admin, "refresh", "*", None, entry, note=note)
    return {"ok": True, **entry}


# ─── Iter 232N.65: Bulk actions ────────────────────────────────────


class BulkActionRequest(BaseModel):
    action: str = Field(..., pattern=r"^(mark_prospect|unmark_prospect|delete)$")
    player_ids: Optional[list[str]] = None
    # Alternative to explicit IDs — apply to every row matching a
    # filter. UI uses `player_ids` from the current selection, but the
    # filter form is handy for scripted cleanup.
    filter_q: Optional[str] = None
    filter_position: Optional[str] = None
    filter_league: Optional[str] = None
    filter_is_prospect: Optional[bool] = None
    note: Optional[str] = None


@router.post("/admin/players/bulk")
async def admin_bulk_action(input: BulkActionRequest, request: Request):
    """Apply `mark_prospect` / `unmark_prospect` / `delete` to a set of
    players either by explicit ID list or by filter query."""
    admin = await _require_admin(request)
    db = _db()

    query: dict = {}
    if input.player_ids:
        object_ids: list[ObjectId] = []
        for pid in input.player_ids:
            try:
                object_ids.append(ObjectId(pid))
            except Exception:
                continue
        if not object_ids:
            raise HTTPException(status_code=400, detail="No valid player_ids")
        query = {"_id": {"$in": object_ids}}
    else:
        if input.filter_q:
            query["name"] = {"$regex": input.filter_q, "$options": "i"}
        if input.filter_position:
            query["position"] = input.filter_position
        if input.filter_league:
            query["league"] = input.filter_league
        if input.filter_is_prospect is not None:
            query["is_prospect"] = bool(input.filter_is_prospect)
        if not query:
            raise HTTPException(
                status_code=400,
                detail="Provide player_ids or at least one filter to scope the bulk action.",
            )

    started_at = datetime.now(timezone.utc)
    affected = 0
    skipped_on_roster = 0

    if input.action in ("mark_prospect", "unmark_prospect"):
        val = input.action == "mark_prospect"
        r = await db.players.update_many(query, {"$set": {"is_prospect": val}})
        affected = r.modified_count
    elif input.action == "delete":
        # Enforce roster safety for every candidate.
        candidates = await db.players.find(query, {"_id": 1}).to_list(length=None)
        for c in candidates:
            pid = str(c["_id"])
            on_roster = await db.teams.count_documents({"roster": pid})
            if on_roster > 0:
                skipped_on_roster += 1
                continue
            await db.players.delete_one({"_id": c["_id"]})
            affected += 1

    entry = {
        "action": input.action,
        "started_at": started_at.isoformat(),
        "affected": affected,
        "skipped_on_roster": skipped_on_roster,
        "scope": {
            "player_ids_count": len(input.player_ids or []),
            "filter": {k: v for k, v in {
                "q": input.filter_q,
                "position": input.filter_position,
                "league": input.filter_league,
                "is_prospect": input.filter_is_prospect,
            }.items() if v is not None},
        },
        "note": input.note,
    }
    await _audit(db, admin, "bulk", "*", None, entry, note=input.note)
    return {"ok": True, **entry}



# ─── Iter 232N.66: Standalone DB-side duplicate detection ──────────


@router.get("/admin/players/duplicates")
async def admin_scan_duplicates(request: Request, limit: int = 200):
    """Scan the existing `db.players` collection for (name+birth_date)
    duplicate clusters, independent of the NHL API sync. Catches
    historical seeding artefacts like the Adam Fantilli-@-Michigan
    ghost row that lingers with a stale nhl_id after the player was
    drafted to the NHL.

    Returns clusters sorted by size DESC so the messiest names surface
    first. The recommended survivor (NHL row, non-admin_-stub,
    non-prospect) is the first entry in each `rows` array.
    """
    await _require_admin(request)
    db = _db()
    # Fetch every row that has a name — matcher uses name-first
    # bucketing and reasons about birth_date presence internally, so
    # we can't skip birth_date-less rows here (that's exactly the
    # Fantilli-@-Michigan case).
    cursor = db.players.find(
        {"name": {"$exists": True, "$nin": [None, ""]}},
        {"nhl_id": 1, "name": 1, "team": 1, "age": 1, "is_prospect": 1,
         "birth_date": 1, "league": 1},
    )
    existing = await cursor.to_list(length=None)
    clusters = nhl_sync.find_db_duplicates(existing)
    limit = max(1, min(int(limit), 500))
    return {
        "ok": True,
        "total_clusters": len(clusters),
        "total_rows_flagged": sum(len(c["rows"]) for c in clusters),
        "clusters": clusters[:limit],
    }


class DedupeMergeRequest(BaseModel):
    # List of merges to apply. Each merge keeps `keep_id` and deletes
    # every id in `drop_ids` (roster-safe). This shape mirrors what the
    # admin sees in the duplicates UI: pick a survivor per cluster,
    # tick the rows to drop.
    merges: list[dict] = Field(..., min_length=1)
    note: Optional[str] = None


@router.post("/admin/players/duplicates/merge")
async def admin_merge_duplicates(input: DedupeMergeRequest, request: Request):
    admin = await _require_admin(request)
    db = _db()
    started_at = datetime.now(timezone.utc)
    merged = 0
    skipped_on_roster = 0
    invalid = 0
    errors: list[str] = []

    for merge in input.merges:
        keep_id = merge.get("keep_id")
        drop_ids = merge.get("drop_ids") or []
        if not keep_id or not drop_ids:
            invalid += 1
            continue
        try:
            keep_obj = await db.players.find_one({"_id": ObjectId(keep_id)})
        except Exception:
            invalid += 1
            continue
        if not keep_obj:
            errors.append(f"keep_id {keep_id} not found")
            continue

        for drop_id in drop_ids:
            if drop_id == keep_id:
                continue
            try:
                on_roster_teams = await db.teams.find(
                    {"roster": drop_id}, {"_id": 1},
                ).to_list(length=None)
            except Exception:
                errors.append(f"roster lookup failed for {drop_id}")
                continue
            if on_roster_teams:
                # Move the roster reference to the survivor before the
                # delete so we don't strand a team without their guy.
                try:
                    for t in on_roster_teams:
                        await db.teams.update_one(
                            {"_id": t["_id"]},
                            {"$pull": {"roster": drop_id}},
                        )
                        await db.teams.update_one(
                            {"_id": t["_id"], "roster": {"$ne": keep_id}},
                            {"$addToSet": {"roster": keep_id}},
                        )
                    # Rewire any contracts stamped with the stale id to
                    # point at the survivor. Best-effort; missing
                    # collection is fine.
                    try:
                        await db.contracts.update_many(
                            {"player_id": drop_id},
                            {"$set": {"player_id": keep_id}},
                        )
                    except Exception:
                        pass
                    skipped_on_roster += 1  # counted as roster-repointed
                except Exception as e:
                    errors.append(f"roster repoint failed for {drop_id}: {str(e)[-80:]}")
                    continue
            try:
                await db.players.delete_one({"_id": ObjectId(drop_id)})
                merged += 1
            except Exception as e:
                errors.append(f"delete failed for {drop_id}: {str(e)[-80:]}")

    entry = {
        "started_at": started_at.isoformat(),
        "merged": merged,
        "roster_repointed": skipped_on_roster,
        "invalid_merges": invalid,
        "errors": errors[:20],
        "note": input.note,
    }
    await _audit(db, admin, "bulk", "*", None, entry, note=input.note or "duplicate merge")
    return {"ok": True, **entry}
