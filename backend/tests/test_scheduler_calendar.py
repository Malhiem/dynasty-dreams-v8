from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.scheduler_calendar import Calendar, can_edit, season_year


def calendar():
    return dict(seasonStart="2026-10-07", seasonEnd="2026-10-20", scoringInterval="weekly", startDay=1,
                mergeWeeks=1, matchupsPerPeriod=1, playoffStart="2026-10-21", playoffEnd="2026-10-27",
                playoffInterval="weekly", regularPeriods=[dict(id=1, type="regular", startDate="2026-10-07", endDate="2026-10-20")],
                playoffPeriods=[dict(id=1, type="playoff", startDate="2026-10-21", endDate="2026-10-27")],
                brackets=[dict(id="championship", name="Champion", teams=2, rounds=1)])


def test_calendar_roundtrip_and_same_day_period():
    data = calendar()
    data["regularPeriods"][0]["endDate"] = "2026-10-07"
    assert Calendar.model_validate(data).model_dump(mode="json") == data


@pytest.mark.parametrize("field,value", [("seasonEnd", "2026-10-01"), ("seasonStart", "2026-02-30"),
    ("seasonEnd", "2028-01-01"), ("scoringInterval", "unknown"), ("matchupsPerPeriod", 0),
    ("matchupsPerPeriod", 1.5), ("startDay", 7), ("mergeWeeks", 4)])
def test_invalid_config(field, value):
    data = calendar(); data[field] = value
    with pytest.raises(ValidationError):
        Calendar.model_validate(data)


@pytest.mark.parametrize("mutation", ["reverse", "outside", "duplicate", "wrong_type", "overlap", "bracket_rounds", "blank_name", "duplicate_bracket", "extra"])
def test_invalid_periods_and_brackets(mutation):
    data = calendar()
    if mutation == "reverse": data["regularPeriods"][0]["endDate"] = "2026-10-06"
    if mutation == "outside": data["regularPeriods"][0]["startDate"] = "2026-10-01"
    if mutation == "duplicate": data["regularPeriods"].append(deepcopy(data["regularPeriods"][0]))
    if mutation == "wrong_type": data["regularPeriods"][0]["type"] = "playoff"
    if mutation == "overlap":
        data["playoffStart"] = "2026-10-20"; data["playoffPeriods"][0]["startDate"] = "2026-10-20"
    if mutation == "bracket_rounds": data["brackets"][0]["teams"] = 8
    if mutation == "blank_name": data["brackets"][0]["name"] = "  "
    if mutation == "duplicate_bracket": data["brackets"].append(deepcopy(data["brackets"][0]))
    if mutation == "extra": data["commissioner_id"] = "attacker"
    with pytest.raises(ValidationError): Calendar.model_validate(data)


def test_authorization_handles_mixed_id_representations():
    from bson import ObjectId
    uid = ObjectId()
    for field, value in [("commissioner_id", str(uid)), ("co_commissioners", [str(uid)]), ("admin_ids", [uid])]:
        assert can_edit({field: value}, {"_id": uid})
    assert not can_edit({"commissioner_id": str(ObjectId())}, {"_id": uid, "role": "admin"})


def test_season_context_prefers_active_season():
    assert season_year({"current_season_year": 2027, "season_start_date": "2026-10-07"}) == 2027
    assert season_year({"season_start_date": "2026-10-07"}) == 2026
