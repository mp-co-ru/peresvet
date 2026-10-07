import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.schedules.app.schedules_app_svc import SchedulesApp


class _Logger:
    def __init__(self):
        self.errors = []
        self.infos = []
        self.debugs = []

    def error(self, msg, *a, **k):
        self.errors.append(msg)

    def info(self, msg, *a, **k):
        self.infos.append(msg)

    def debug(self, msg, *a, **k):
        self.debugs.append(msg)


class _Job:
    pass


class _Scheduler:
    def __init__(self):
        self.jobs = {}
        self.started = False
        self.stopped = False
        self.running = False

    def add_job(self, func, kind, **kwargs):
        self.jobs[kwargs["id"]] = kwargs

    def get_job(self, schedule_id):
        return self.jobs.get(schedule_id)

    def remove_job(self, schedule_id):
        self.jobs.pop(schedule_id, None)

    def start(self):
        self.started = True
        self.running = True

    def shutdown(self, wait=False):
        self.stopped = True
        self.running = False


def _svc(search=None):
    svc = object.__new__(SchedulesApp)
    svc._scheduler = _Scheduler()
    svc._hierarchy = SimpleNamespace(search=search or AsyncMock(return_value=[]))
    svc._logger = _Logger()
    svc._config = SimpleNamespace(svc_name="schedules_app", hierarchy={"class": "prsSchedule"})
    svc._post_message = AsyncMock()
    return svc


def test_start_stop_and_generate_event():
    svc = _svc()
    cfg = {"interval_type": "seconds", "interval_value": 5, "start": 1_000_000, "end": 2_000_000}
    asyncio.run(svc.start_schedule("s1", cfg))
    assert "s1" in svc._scheduler.jobs
    assert svc._scheduler.jobs["s1"]["seconds"] == 5
    asyncio.run(svc.start_schedule("s2", {**cfg, "interval_type": "minutes"}))
    assert svc._scheduler.jobs["s2"]["minutes"] == 5
    asyncio.run(svc.start_schedule("s3", {**cfg, "interval_type": "hours"}))
    asyncio.run(svc.start_schedule("s4", {**cfg, "interval_type": "days"}))
    asyncio.run(svc.stop_schedule("s1"))
    assert "s1" not in svc._scheduler.jobs
    asyncio.run(svc.stop_schedule("missing"))
    asyncio.run(svc._generate_event("s2"))
    svc._post_message.assert_awaited()
    rk = svc._post_message.await_args.kwargs["routing_key"]
    assert rk == "prsSchedule.app.fire_event.s2"


def test_created_updated_deleted_and_startup():
    sid = "sched-1"
    row = [(sid, None, {"prsActive": ["TRUE"], "prsJsonConfigString": [json.dumps({
        "interval_type": "seconds", "interval_value": 1, "start": 1
    })]})]

    async def search(payload):
        return row

    svc = _svc(search=search)
    asyncio.run(svc._created({"id": sid}))
    assert sid in svc._scheduler.jobs

    inactive = _svc(search=AsyncMock(return_value=[(sid, None, {"prsActive": ["FALSE"], "prsJsonConfigString": ["{}"]})]))
    asyncio.run(inactive._created({"id": sid}))
    assert sid not in inactive._scheduler.jobs

    missing = _svc(search=AsyncMock(return_value=[]))
    asyncio.run(missing._created({"id": sid}))
    assert missing._logger.errors

    badjson = _svc(search=AsyncMock(return_value=[(sid, None, {"prsActive": ["TRUE"], "prsJsonConfigString": ["not-json"]})]))
    asyncio.run(badjson._created({"id": sid}))

    svc2 = _svc(search=search)
    asyncio.run(svc2.start_schedule(sid, {"interval_type": "seconds", "interval_value": 1, "start": 1}))
    asyncio.run(svc2._updated({"id": sid}))
    asyncio.run(svc2._deleted({"id": sid}))
    assert sid not in svc2._scheduler.jobs

    started = _svc(search=AsyncMock(return_value=[
        (sid, None, {"prsJsonConfigString": [json.dumps({"interval_type": "seconds", "interval_value": 1, "start": 1})]}),
        ("s-bad", None, {"prsJsonConfigString": [None]}),
        ("s-err", None, {"prsJsonConfigString": ["{"]}),
    ]))
    parent = SchedulesApp.__bases__[0]
    orig = parent.on_startup

    async def skip(self):
        return None

    parent.on_startup = skip
    try:
        asyncio.run(started.on_startup())
    finally:
        parent.on_startup = orig
    assert started._scheduler.started is True

    started._scheduler.running = True
    orig_off = parent.on_shutdown

    async def skip_off(self):
        return None

    parent.on_shutdown = skip_off
    try:
        asyncio.run(started.on_shutdown())
    finally:
        parent.on_shutdown = orig_off
    assert started._scheduler.stopped is True
