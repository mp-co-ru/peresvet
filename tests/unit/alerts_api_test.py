import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.alerts.app_api.alerts_app_api_settings import AlertsAppAPISettings
from src.services.alerts.app_api.alerts_app_api_svc import (
    AckAlarm,
    AlarmsGet,
    AlertsAppAPI,
)

ALERT = "1500c712-726a-103e-9264-a5021ec2dae1"


def test_ack_without_timestamp_uses_current_time(monkeypatch):
    import src.services.alerts.app_api.alerts_app_api_svc as mod

    monkeypatch.setattr(mod.t, "now_int", lambda: 424242)
    alarm = AckAlarm.model_validate({"id": ALERT})
    assert alarm.x == 424242
    explicit = AckAlarm.model_validate({"id": ALERT, "x": 7})
    assert explicit.x == 7


def _api(response):
    svc = object.__new__(AlertsAppAPI)
    svc._config = SimpleNamespace(hierarchy={"class": "prsAlert"})
    svc._post_message = AsyncMock(return_value=response)
    return svc


def test_alarms_get_formats_fired_finish_and_acked():
    svc = _api({
        "data": [{
            "id": ALERT,
            "cn": "Высокий уровень",
            "description": "",
            "tagId": "tag",
            "fired": 1_000_000,
            "finish": None,
            "acked": 2_000_000,
        }]
    })
    payload = AlarmsGet.model_validate({"format": True, "fired": True})
    res = asyncio.run(svc.alarms_get(payload))
    item = res["data"][0]
    assert isinstance(item["fired"], datetime)
    assert item["finish"] is None
    assert isinstance(item["acked"], datetime)
    assert "start" not in item


def test_alerts_api_addresses_the_alert_service():
    settings = AlertsAppAPISettings()
    assert settings.hierarchy["class"] == "prsAlert"
    svc = object.__new__(AlertsAppAPI)
    svc._config = settings
    svc._post_message = AsyncMock(return_value={"data": []})
    asyncio.run(svc.alarms_get(AlarmsGet.model_validate({"fired": False})))
    assert svc._post_message.await_args.kwargs["routing_key"] == "prsAlert.app_api.get_alarms"


def test_alarms_get_forwards_interval_and_count():
    svc = _api({
        "data": [{"fired": 1_000_000, "finish": 2_000_000, "acked": None}],
    })
    payload = AlarmsGet.model_validate({
        "parentId": ALERT,
        "fired": False,
        "start": 10,
        "finish": 20,
        "format": True,
        "count": 5,
    })
    res = asyncio.run(svc.alarms_get(payload))
    kwargs = svc._post_message.await_args.kwargs
    assert kwargs["routing_key"] == "prsAlert.app_api.get_alarms"
    assert kwargs["mes"]["parentId"] == [ALERT]
    assert kwargs["mes"]["fired"] is False
    assert kwargs["mes"]["start"] == 10
    assert kwargs["mes"]["finish"] == 20
    assert kwargs["mes"]["count"] == 5
    assert isinstance(res["data"][0]["fired"], datetime)
    assert res["data"][0]["acked"] is None


def test_alarms_get_count_is_empty_until_set():
    payload = AlarmsGet.model_validate({"fired": True})
    assert payload.count is None
    assert payload.fired is True
    clamped = AlarmsGet.model_validate({"fired": False, "count": 900})
    assert clamped.count == 500


def test_alarms_get_without_reply_is_an_error():
    svc = _api(None)
    payload = AlarmsGet.model_validate({"fired": True})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.alarms_get(payload))
    assert exc.value.status_code == 503
