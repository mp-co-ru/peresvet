from src.services.schedules.api_crud.schedules_api_crud_svc import ScheduleCreate


def test_schedule_start_defaults_to_creation_time(monkeypatch):
    import src.services.schedules.api_crud.schedules_api_crud_svc as mod

    stamp = {"n": 0}

    def now():
        stamp["n"] += 1
        return 1_700_000_000_000_000 + stamp["n"] * 60_000_000

    monkeypatch.setattr(mod.t, "now_int", now)
    first = ScheduleCreate.model_validate({"attributes": {}})
    second = ScheduleCreate.model_validate({"attributes": {}})
    assert first.attributes.prsJsonConfigString["start"] != second.attributes.prsJsonConfigString["start"]
