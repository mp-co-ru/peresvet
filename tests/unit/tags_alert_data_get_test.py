import asyncio
from types import SimpleNamespace

from src.services.tags.app.tags_app_svc import TagsApp

ALERT = "1500c712-726a-103e-9264-a5021ec2dae1"


class _Logger:
    def error(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


class _Json:
    async def get(self, *a, **k):
        return None

    async def delete(self, *a, **k):
        return None

    async def set(self, *a, **k):
        return True


class _Redis:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def json(self):
        return _Json()


def test_data_get_for_alert_is_422_not_500():
    svc = object.__new__(TagsApp)
    svc._config = SimpleNamespace(svc_name="tags_app")
    svc._logger = _Logger()
    svc._cache = SimpleNamespace(get_redis=lambda: _Redis())

    async def search(payload):
        return [(
            ALERT,
            "dn",
            {
                "prsActive": ["TRUE"],
                "prsValueTypeCode": [None],
                "prsMaxLineDev": [None],
                "objectClass": ["prsAlert"],
            },
        )]

    svc._hierarchy = SimpleNamespace(search=search)
    res = asyncio.run(svc.data_get({"tagId": [ALERT]}))
    assert res["error"]["code"] == 422
    assert "GET /v1/alarms/" in res["error"]["message"]
