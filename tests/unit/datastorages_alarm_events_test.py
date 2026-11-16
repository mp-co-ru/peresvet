import asyncio
from types import SimpleNamespace

from src.services.dataStorages.app.dataStorages_app_base import alarm_event_body
from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc import (
    DataStoragesAppPostgreSQL,
)


class _Logger:
    def __init__(self):
        self.errors = []

    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def error(self, self_msg=None, *a, **k):
        self.errors.append(self_msg)


class _RedisJson:
    def __init__(self, store):
        self.store = store

    async def get(self, name, *a, **k):
        return self.store.get(name)


class _Redis:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def json(self):
        return _RedisJson(self.store)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        return self._walk()

    async def _walk(self):
        for row in self.rows:
            yield row


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.copied = []
        self.executed = []
        self.fetched = None

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def cursor(self, *q):
        return _Cursor(self.rows)

    async def copy_records_to_table(self, table, records, columns):
        self.copied.append((table, records, columns))

    async def execute(self, query):
        self.executed.append(query)

    async def fetchrow(self, query):
        self.fetched = query
        if not self.rows:
            return None
        row = self.rows[0]
        return {"x": row["x"], "cx": row["cx"], "e": row["e"]}


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return self.conn


def _svc(rows):
    conn = _Conn(rows)
    svc = object.__new__(DataStoragesAppPostgreSQL)
    svc._config = SimpleNamespace(svc_name="dataStorages_app_postgresql")
    svc._logger = _Logger()
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis({
        "a1.dataStorages_app_postgresql": {"dss": {"ds": {"table": "a_a1"}}},
    }))
    svc._connection_pools = {"ds": _Pool(conn)}
    return svc, conn


def test_alarm_event_body_accepts_flat_and_wrapped_forms():
    assert alarm_event_body({"alertId": "a", "x": 1}) == {"alertId": "a", "x": 1}
    assert alarm_event_body({"data": {"alertId": "a", "x": 2}})["x"] == 2


def test_alarm_on_off_and_ack_write_x_e_and_cx():
    svc, conn = _svc([])
    asyncio.run(svc._alarm_on({"alertId": "a1", "x": 100}))
    assert conn.copied == [("a_a1", [(100, None, None)], ("x", "cx", "e"))]

    svc, conn = _svc([{"id": 7, "x": 100, "cx": None, "e": None}])
    asyncio.run(svc._alarm_off({"alertId": "a1", "x": 180}))
    assert conn.executed == ['update "a_a1" set e = 180 where id = 7']

    svc, conn = _svc([{"id": 7, "x": 100, "cx": None, "e": 180}])
    asyncio.run(svc._alarm_ack({"data": {"alertId": "a1", "x": 200}}))
    assert conn.executed == ['update "a_a1" set cx = 200 where id = 7']

    svc, conn = _svc([{"id": 7, "x": 100, "cx": None, "e": None}])
    state = asyncio.run(svc._alarm_state({"alertId": "a1"}))
    assert state == {"alertId": "a1", "x": 100, "cx": None, "e": None}
