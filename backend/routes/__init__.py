"""Modular FastAPI routers extracted from server.py.

Each module exposes:
  - `router`: APIRouter instance with routes registered
  - `setup(deps: dict)`: function to inject shared deps (db, sio, helpers)
    BEFORE the router is included in the main app.

Usage in server.py (after all helpers are defined):

    from routes import awards, drafts, matchups
    deps = {
        "db": db, "sio": sio, "logger": logger,
        "get_current_user": get_current_user,
        "_safe_object_id": _safe_object_id,
        "_evaluate_conditions": _evaluate_conditions,
        "_execute_trade": _execute_trade,
        "calculate_fantasy_points": calculate_fantasy_points,
    }
    awards.setup(deps); api_router.include_router(awards.router)
    drafts.setup(deps); api_router.include_router(drafts.router)
    matchups.setup(deps); api_router.include_router(matchups.router)
"""
