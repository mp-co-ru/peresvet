"""Подхват и отдача: nodes в конфигурации, байты по HTTP, брокер только для адреса."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.common.app_svc import AppSvc
from src.services.tags.app_api.tags_app_api_svc import DataGet

ROOT = Path(__file__).resolve().parents[2]
TAG = "1500c712-726a-103e-9264-a5021ec2dae1"
OTHER = "2500c712-726a-103e-9264-a5021ec2dae1"
CONN = "3500c712-726a-103e-9264-a5021ec2dae1"
CAMERA_URL = "rtsp://192.168.1.72:554/live/ch00_0"


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class _Channel:
    def __init__(self):
        self.names = []

    async def declare_queue(self, name, durable=False, auto_delete=True):
        self.names.append(name)
        return name


class _Hierarchy:
    def __init__(self, by_id, connectors, links, storages=None):
        self.by_id = by_id
        self.connectors = connectors
        self.links = links
        self.storages = storages or []

    async def search(self, payload):
        if payload.get("id"):
            tag_id = payload["id"]
            if isinstance(tag_id, list):
                tag_id = tag_id[0]
            return self.by_id.get(tag_id, [])
        if payload.get("base") == "cn=connectors,cn=prs":
            return self.connectors
        if payload.get("base") == "cn=dataStorages,cn=prs":
            return self.storages
        return self.links.get(payload.get("base"), [])


def _video_tag():
    return [(TAG, "dn", {"prsValueTypeCode": ["6"], "prsActive": ["TRUE"]})]


def _camera_connector():
    return [(
        CONN,
        "dn",
        {
            "prsEntityTypeCode": ["10"],
            "prsActive": ["TRUE"],
            "prsJsonConfigString": [json.dumps({"rtspUrl": CAMERA_URL})],
        },
    )]


def _bound():
    return _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {
            CONN: [(TAG, "dn", {"cn": [TAG]})],
            "ds-video": [("store-link", "dn", {"cn": [TAG]})],
        },
        [(
            "ds-video",
            "dn",
            {
                "prsEntityTypeCode": ["3"],
                "prsActive": ["TRUE"],
                "prsJsonConfigString": ['{"archivePath": "/var/lib/peresvet/video", "retentionHours": 24}'],
            },
        )],
    )


def _request(path: str, query: str, method: str = "GET", body: bytes = b"") -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"content-type", b"application/json")] if body else [],
        "query_string": query.encode(),
    }, receive)


def test_capture_with_nodes_skips_created_and_names_the_queue_after_the_first_id():
    from src.services.video.video_capture_settings import VideoCaptureSettings
    from src.services.video.video_capture_svc import VideoCapture

    app = object.__new__(VideoCapture)
    app._handlers = {}
    app._config = VideoCaptureSettings(nodes=[CONN, OTHER])
    AppSvc._set_handlers(app)
    assert "prsConnector.model.created" not in app._handlers
    for event in ("may_update", "updating", "updated", "may_delete", "deleting", "deleted"):
        assert f"prsConnector.model.{event}.{CONN}" in app._handlers
        assert f"prsConnector.model.{event}.{OTHER}" in app._handlers
    assert f"video.capture.lookup.{CONN}" in app._handlers
    assert f"video.capture.lookup.{OTHER}" in app._handlers
    assert "video.capture.lookup.*" not in app._handlers
    assert "prsTag.model.updated.*" in app._handlers
    assert "prsTag.model.deleted.*" in app._handlers
    assert not any(key.startswith("prsTag.model.may_") for key in app._handlers)
    channel = _Channel()
    app._amqp_channel = channel
    asyncio.run(AppSvc._generate_queue(app))
    assert channel.names == [f"video_capture_consume_{CONN}"]


def test_capture_scan_starts_only_listed_cameras_and_stops_the_rest(monkeypatch):
    from src.services.video import video_capture_svc

    searches = []
    synced = []
    stopped = []

    async def search(payload):
        searches.append(payload)
        return [(
            CONN,
            "dn",
            {
                "prsActive": ["TRUE"],
                "prsJsonConfigString": [json.dumps({"rtspUrl": CAMERA_URL})],
            },
        )]

    def sync_session(conn_id, camera, directory=None):
        synced.append(conn_id)
        return "kept"

    async def stop_session(conn_id):
        stopped.append(conn_id)
        return True

    async def stored_camera(_hierarchy, conn_id, camera):
        return camera

    monkeypatch.setattr(video_capture_svc, "sync_session", sync_session)
    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)
    monkeypatch.setattr(video_capture_svc, "tracked_session_ids", lambda: [CONN, OTHER])
    monkeypatch.setattr(video_capture_svc, "camera_for_session", stored_camera)
    svc = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(nodes=[CONN], svc_name="video_capture"),
        _logger=_Logger(),
    )
    asyncio.run(video_capture_svc.VideoCapture._scan_once(svc))
    assert searches[0]["id"] == [CONN]
    assert "base" not in searches[0]
    assert synced == [CONN]
    assert stopped == [OTHER]


def _camera_attrs():
    return {
        "prsEntityTypeCode": ["10"],
        "prsActive": ["TRUE"],
        "prsJsonConfigString": [json.dumps({"rtspUrl": CAMERA_URL})],
    }


class _TagGateHierarchy:
    def __init__(self, active: str):
        self.active = active
        self.calls = []

    async def search(self, payload):
        self.calls.append(payload)
        if payload.get("id") in ([CONN], CONN):
            return [(CONN, "dn", _camera_attrs())]
        if payload.get("base") == "cn=connectors,cn=prs":
            return [(CONN, "dn", _camera_attrs())]
        if payload.get("base") == CONN and payload.get("filter", {}).get("objectClass") == ["prsConnectorTagData"]:
            return [("link", "dn", {"cn": [TAG]})]
        if payload.get("base") == CONN:
            return [(TAG, "dn", {"cn": [TAG]})]
        if payload.get("id") in ([TAG], TAG):
            if self.active is None:
                return []
            return [(TAG, "dn", {"prsValueTypeCode": ["6"], "prsActive": [self.active]})]
        if payload.get("base") == "cn=dataStorages,cn=prs":
            return [(
                "ds-video",
                "dn",
                {
                    "prsEntityTypeCode": ["3"],
                    "prsActive": ["TRUE"],
                    "prsJsonConfigString": ['{"archivePath": "/var/lib/peresvet/video", "retentionHours": 24}'],
                },
            )]
        if (
            payload.get("base") == "ds-video"
            and payload.get("filter", {}).get("objectClass") == ["prsDatastorageTagData"]
        ):
            return [("store-link", "dn", {"cn": [TAG]})]
        return []


def test_inactive_video_tag_stops_capture_and_active_tag_starts_it(monkeypatch):
    from src.services.video import video_capture_svc

    synced = []
    stopped = []

    def sync_session(conn_id, camera, directory=None):
        synced.append(conn_id)
        return "restart"

    async def stop_session(conn_id):
        stopped.append(conn_id)
        return True

    monkeypatch.setattr(video_capture_svc, "sync_session", sync_session)
    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)

    inactive = _TagGateHierarchy("FALSE")
    svc = SimpleNamespace(
        _hierarchy=inactive,
        _config=SimpleNamespace(nodes=[], svc_name="video_capture"),
        _logger=_Logger(),
    )
    svc._apply_tag = video_capture_svc.VideoCapture._apply_tag.__get__(svc, SimpleNamespace)
    svc._apply_connector = video_capture_svc.VideoCapture._apply_connector.__get__(svc, SimpleNamespace)
    asyncio.run(video_capture_svc.VideoCapture._tag_updated(svc, {"id": TAG}))
    assert synced == []
    assert stopped == [CONN]

    stopped.clear()
    active = _TagGateHierarchy("TRUE")
    svc._hierarchy = active
    asyncio.run(video_capture_svc.VideoCapture._tag_updated(svc, {"id": TAG}))
    assert synced == [CONN]
    assert stopped == []


def test_scan_skips_a_camera_without_an_active_video_tag(monkeypatch):
    from src.services.video import video_capture_svc

    synced = []
    stopped = []

    def sync_session(conn_id, camera, directory=None):
        synced.append(conn_id)
        return "kept"

    async def stop_session(conn_id):
        stopped.append(conn_id)
        return True

    monkeypatch.setattr(video_capture_svc, "sync_session", sync_session)
    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)
    monkeypatch.setattr(video_capture_svc, "tracked_session_ids", lambda: [CONN])
    svc = SimpleNamespace(
        _hierarchy=_TagGateHierarchy("FALSE"),
        _config=SimpleNamespace(nodes=[], svc_name="video_capture"),
        _logger=_Logger(),
    )
    asyncio.run(video_capture_svc.VideoCapture._scan_once(svc))
    assert synced == []
    assert stopped == [CONN]


def test_ordinary_tag_update_does_not_touch_the_camera_session(monkeypatch):
    from src.services.video import video_capture_svc

    async def stop_session(conn_id):
        raise AssertionError(conn_id)

    def sync_session(*args, **kwargs):
        raise AssertionError(args)

    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)
    monkeypatch.setattr(video_capture_svc, "sync_session", sync_session)

    async def search(payload):
        assert payload["id"] in ([TAG], TAG)
        return [(TAG, "dn", {"prsValueTypeCode": ["1"], "prsActive": ["FALSE"]})]

    svc = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(nodes=[], svc_name="video_capture"),
        _logger=_Logger(),
    )
    svc._apply_tag = video_capture_svc.VideoCapture._apply_tag.__get__(svc, SimpleNamespace)
    svc._apply_connector = video_capture_svc.VideoCapture._apply_connector.__get__(svc, SimpleNamespace)
    asyncio.run(video_capture_svc.VideoCapture._tag_updated(svc, {"id": TAG}))


def test_connector_outside_nodes_does_not_open_a_session(monkeypatch):
    from src.services.video import video_capture_svc

    stopped = []

    async def search(payload):
        raise AssertionError(payload)

    async def stop_session(conn_id):
        stopped.append(conn_id)
        return True

    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)
    svc = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(nodes=[OTHER], svc_name="video_capture"),
        _logger=_Logger(),
    )
    svc._apply_connector = video_capture_svc.VideoCapture._apply_connector.__get__(svc, SimpleNamespace)
    asyncio.run(svc._apply_connector(CONN))
    assert stopped == [CONN]


def test_capture_lookup_returns_its_own_base_url():
    from src.services.video.video_capture_svc import VideoCapture

    svc = SimpleNamespace(
        _config=SimpleNamespace(nodes=[], http_base_url="http://video-capture:8091/"),
    )
    reply = asyncio.run(VideoCapture._lookup(svc, {"connectorId": CONN}))
    assert reply == {"baseUrl": "http://video-capture:8091"}


def test_may_update_does_not_stop_the_session(monkeypatch):
    from src.services.video import video_capture_svc

    async def stop_session(conn_id):
        raise AssertionError(conn_id)

    monkeypatch.setattr(video_capture_svc, "stop_session", stop_session)
    svc = object.__new__(video_capture_svc.VideoCapture)
    assert asyncio.run(video_capture_svc.VideoCapture._may_update(svc, {"id": CONN})) == {
        "response": True,
    }


def test_delivery_does_not_subscribe_to_tag_model_or_data_get():
    from src.services.video.video_delivery_settings import VideoDeliverySettings
    from src.services.video.video_delivery_svc import VideoDelivery

    assert "_set_handlers" in VideoDelivery.__dict__
    app = object.__new__(VideoDelivery)
    app._handlers = {}
    app._config = VideoDeliverySettings()
    VideoDelivery._set_handlers(app)
    assert "video.delivery.locate.*" in app._handlers
    assert not any("prsTag" in key or "data_get" in key for key in app._handlers)
    app._handlers = {}
    app._config = VideoDeliverySettings(nodes=[TAG])
    VideoDelivery._set_handlers(app)
    assert list(app._handlers) == [f"video.delivery.locate.{TAG}"]
    reply = asyncio.run(VideoDelivery._locate(app, {"tagId": TAG}))
    assert reply == {"baseUrl": "http://video-delivery:8092"}
    channel = _Channel()
    app._amqp_channel = channel
    asyncio.run(AppSvc._generate_queue(app))
    assert channel.names == [f"video_delivery_consume_{TAG}"]


def test_delivery_rejects_a_foreign_tag_without_calling_capture(monkeypatch):
    from src.services.video import delivery_http

    async def locate_capture(*args, **kwargs):
        raise AssertionError("подхват")

    monkeypatch.setattr(delivery_http, "locate_capture", locate_capture)
    app = SimpleNamespace(
        _config=SimpleNamespace(nodes=[OTHER], svc_name="video_delivery"),
        _logger=_Logger(),
    )
    response = asyncio.run(
        delivery_http.delivery_data_response(app, _request("/v1/data/", f"tagId={TAG}"))
    )
    assert response.status_code == 404


def test_delivery_live_url_comes_from_capture_lookup(monkeypatch):
    from src.services.video import delivery_http

    called = {}

    async def post_message(mes, reply=False, routing_key=None):
        called["key"] = routing_key
        called["mes"] = mes
        return {"baseUrl": "http://video-capture:8091"}

    async def proxy_stream(request, url, forward_query=True):
        called["url"] = url
        called["forward"] = forward_query
        return JSONResponse({"ok": True})

    monkeypatch.setattr(delivery_http, "proxy_stream", proxy_stream)
    app = SimpleNamespace(
        _hierarchy=_bound(),
        _config=SimpleNamespace(nodes=[], svc_name="video_delivery"),
        _logger=_Logger(),
        _post_message=post_message,
    )
    response = asyncio.run(
        delivery_http.delivery_data_response(app, _request("/v1/data/", f"tagId={TAG}&audio=1"))
    )
    assert response.status_code == 200
    assert called["key"] == f"video.capture.lookup.{CONN}"
    assert called["mes"] == {"connectorId": CONN}
    assert called["url"] == f"http://video-capture:8091/internal/video/{CONN}/audio"
    assert called["forward"] is False


def test_missing_delivery_is_503_and_not_history(monkeypatch):
    from src.services.video import http_response

    async def post_message(mes, reply=False, routing_key=None):
        return None

    app = SimpleNamespace(
        _hierarchy=_bound(),
        _logger=_Logger(),
        _config=SimpleNamespace(svc_name="tags_app_api", hierarchy={"class": "prsTag"}),
        _post_message=post_message,
    )
    response = asyncio.run(
        http_response.maybe_video_data_response(
            app,
            DataGet.model_validate({"tagId": TAG}),
            _request("/v1/data/", f"tagId={TAG}"),
        )
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert json.loads(response.body)["error"]["message"] == "Сервис отдачи видео не запущен."


def test_public_ptz_authorizes_then_proxies_to_delivery(monkeypatch):
    from src.services.video import ptz_http

    order = []

    async def authorize(action, **kwargs):
        order.append(action)

    async def post_message(mes, reply=False, routing_key=None):
        order.append(routing_key)
        return {"baseUrl": "http://video-delivery:8092/"}

    async def proxy_exchange(request, url, timeout_total=15):
        order.append(url)
        return JSONResponse({"ok": True})

    monkeypatch.setattr(ptz_http, "authorize_action", authorize)
    monkeypatch.setattr(ptz_http, "proxy_exchange", proxy_exchange)
    app = SimpleNamespace(
        _hierarchy=_bound(),
        _logger=_Logger(),
        _config=SimpleNamespace(svc_name="tags_app_api", hierarchy={"class": "prsTag"}),
        _post_message=post_message,
    )
    raw = json.dumps({"tagId": TAG, "action": "stop"}).encode()
    response = asyncio.run(ptz_http.ptz_response(app, _request("/v1/ptz/", "", "POST", raw)))
    assert response.status_code == 200
    assert order == [
        "prsConnector.connector_command",
        f"video.delivery.locate.{TAG}",
        "http://video-delivery:8092/v1/ptz/",
    ]


def test_capture_ptz_refuses_a_camera_outside_nodes(monkeypatch):
    from src.services.video import capture_http

    async def perform_ptz(camera, command):
        raise AssertionError(command)

    monkeypatch.setattr(capture_http, "perform_ptz", perform_ptz)
    app = SimpleNamespace(_config=SimpleNamespace(nodes=[OTHER]))
    response = asyncio.run(capture_http.capture_ptz(app, CONN, {"action": "stop"}))
    assert response.status_code == 404


def test_video_bytes_are_not_configured_as_a_broker_url():
    compose = (ROOT / "docker/compose/docker-compose.video.yml").read_text(encoding="utf-8")
    restart = (ROOT / "docker/compose/docker-compose.restart.yml").read_text(encoding="utf-8")
    assert "VIDEO_SERVER_URL" not in compose
    assert "prs-video-capture" in compose
    assert "prs-video-delivery" in compose
    assert "ports:" not in compose
    assert "container_name: prs-video\n" not in restart
    assert "prs-video-capture" in restart
    assert "prs-video-delivery" in restart
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "VIDEO_SERVER_URL" not in text, path
    nginx = (
        ROOT / "config/nginx/peresvet/locations/peresvet.locations.conf.template"
    ).read_text(encoding="utf-8")
    upstreams = (
        ROOT / "config/nginx/peresvet/upstreams/peresvet.upstreams.conf.template"
    ).read_text(encoding="utf-8")
    assert "proxy_buffering off" in nginx
    assert "proxy_pass http://tags_app_api;" in nginx
    assert "video-capture" not in upstreams
    assert "video-delivery" not in upstreams
