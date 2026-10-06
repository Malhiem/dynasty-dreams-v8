"""Salary bounds for roster edits, using the shared assignment payroll."""
from fastapi import HTTPException
from services.salary_policy import payroll


async def validate_roster_salary(db, team, league, lineup):
    state = await payroll(db, {**team, "lineup": lineup}, league)
    used = state["used"]
    warnings = []
    bounds = [("salary_cap_enabled", "salary_cap", "over_cap", lambda value: used > value),
              ("cap_floor_enabled", "cap_floor", "below_floor", lambda value: used < value)]
    for enabled, field, code, violated in bounds:
        if league.get(enabled) and violated(float(league.get(field) or 0)):
            message = f"Salary violation: payroll ${used:,.0f} is {'over the cap' if code == 'over_cap' else 'below the floor'} (${float(league.get(field) or 0):,.0f})."
            detail = {"code": code, "message": message, "projected_payroll": used}
            if league.get("salary_adherence_mode") == "strict":
                raise HTTPException(409, detail=detail)
            warnings.append(detail)
    return warnings, used
