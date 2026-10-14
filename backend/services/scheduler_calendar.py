"""Validated, season-scoped scoring calendars. Saving never replaces live matchups."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=1, le=366, strict=True)
    startDate: date
    endDate: date
    type: Literal["regular", "playoff"]

    @model_validator(mode="after")
    def ordered(self):
        if self.endDate < self.startDate:
            raise ValueError("Period end must be on or after its start")
        return self


class Bracket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    rounds: int = Field(ge=1, le=7, strict=True)
    teams: int = Field(ge=2, le=100, strict=True)

    @model_validator(mode="after")
    def valid_bracket(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Bracket name is required")
        if 2 ** self.rounds < self.teams:
            raise ValueError("Bracket needs enough rounds to crown a champion")
        return self


class Calendar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seasonStart: date
    seasonEnd: date
    scoringInterval: Literal["daily", "weekly", "biweekly", "monthly"]
    startDay: int = Field(ge=0, le=6, strict=True)  # UTC Sunday = 0
    mergeWeeks: int = Field(ge=1, le=3, strict=True)
    matchupsPerPeriod: int = Field(ge=1, le=99, strict=True)
    playoffStart: date
    playoffEnd: date
    playoffInterval: Literal["daily", "weekly", "biweekly", "monthly"]
    regularPeriods: list[Period] = Field(max_length=366)
    playoffPeriods: list[Period] = Field(max_length=366)
    brackets: list[Bracket] = Field(max_length=50)

    @model_validator(mode="after")
    def valid_calendar(self):
        for start, end in [(self.seasonStart, self.seasonEnd), (self.playoffStart, self.playoffEnd)]:
            if end < start or (end - start).days > 365:
                raise ValueError("Date ranges must be ordered and no longer than 366 days")
        previous = None
        for kind, periods, start, end in [
            ("regular", self.regularPeriods, self.seasonStart, self.seasonEnd),
            ("playoff", self.playoffPeriods, self.playoffStart, self.playoffEnd),
        ]:
            ids = set()
            for period in periods:
                if period.type != kind or period.id in ids:
                    raise ValueError("Period types and IDs must match their section")
                ids.add(period.id)
                if not start <= period.startDate <= period.endDate <= end:
                    raise ValueError("Periods must stay within their configured dates")
                if previous is not None and period.startDate <= previous:
                    raise ValueError("Scoring periods cannot overlap or be out of order")
                previous = period.endDate
        if len({b.id for b in self.brackets}) != len(self.brackets):
            raise ValueError("Bracket IDs must be unique")
        return self


def season_year(league):
    return int(league.get("current_season_year") or str(league.get("season_start_date") or date.today().isoformat())[:4])


def can_edit(league, user):
    uid = str(user["_id"])
    return uid == str(league.get("commissioner_id")) or any(
        uid == str(value) for value in (league.get("co_commissioners") or []) + (league.get("admin_ids") or [])
    )
