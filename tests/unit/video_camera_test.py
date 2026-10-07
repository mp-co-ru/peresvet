"""Тег типа 6 и коннектор-камера: режим чтения, архив, отказ от MQTT."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from pathlib import Path

import pytest
from starlette.responses import JSONResponse

from src.common.consts import CNConnectorTypes, CNTagValueTypes
from src.common.tag_max_line_dev import should_discard_data_point
from src.services.tags.app_api.tags_app_api_svc import DataGet
from src.services.video.camera import (
    fragment_ffmpeg_args,
    is_camera_connector,
    list_segments,
    parse_camera_config,
    redact_rtsp,
    segment_at,
    segments_overlapping,
    session_ffmpeg_args,
    snapshot_file_args,
    video_get_mode,
    write_concat_list,
)
from src.services.video.http_response import maybe_video_data_response
from src.services.video.lookup import resolve_video_get

TAG = "1500c712-726a-103e-9264-a5021ec2dae1"
OTHER = "2500c712-726a-103e-9264-a5021ec2dae1"
CONN = "3500c712-726a-103e-9264-a5021ec2dae1"
CAMERA_URL = "rtsp://192.168.1.72:554/live/ch00_0"


def test_video_type_and_camera_connector_codes():
    assert CNTagValueTypes.CN_VIDEO == 6
    assert CNConnectorTypes.CN_CAMERA == 10
    assert is_camera_connector("10") is True
    assert is_camera_connector(10) is True
    assert is_camera_connector(0) is False
    assert is_camera_connector(None) is False
    assert is_camera_connector("mqtt") is False


def test_video_point_filter_keeps_quality_change_only():
    assert should_discard_data_point(6, 0, None, 0, None, 0) is True
    assert should_discard_data_point(6, 5, None, 0, None, 102) is False
    assert should_discard_data_point(6, 5, None, 102, "кадр", 102) is False


def test_get_mode_follows_keys_the_client_sent():
    assert video_get_mode(set()) == "live"
    assert video_get_mode({"finish"}) == "snapshot"
    assert video_get_mode({"start", "finish"}) == "fragment"
    assert video_get_mode({"start"}) == "fragment"
    assert video_get_mode({"timeStep"}) == "unsupported"
    assert video_get_mode({"count", "finish"}) == "unsupported"

    live = DataGet.model_validate({"tagId": TAG})
    assert "finish" not in live.model_fields_set
    assert video_get_mode(set(live.model_fields_set)) == "live"
    shot = DataGet.model_validate({"tagId": TAG, "finish": 1_000_000})
    assert video_get_mode(set(shot.model_fields_set)) == "snapshot"
    clip = DataGet.model_validate({"tagId": TAG, "start": 1, "finish": 2})
    assert video_get_mode(set(clip.model_fields_set)) == "fragment"


def test_parse_camera_accepts_working_rtsp_and_hides_password():
    camera = parse_camera_config({
        "rtspUrl": CAMERA_URL,
        "archivePath": "/var/lib/peresvet/video/cam-1",
        "retentionHours": 12,
    })
    assert camera.transport == "tcp"
    assert camera.rtsp_url == CAMERA_URL
    assert camera.archive_path == Path("/var/lib/peresvet/video/cam-1")
    assert camera.retention_hours == 12
    assert camera.log_target == "rtsp://192.168.1.72:554/live/ch00_0"
    secret = parse_camera_config({
        "rtspUrl": "rtsp://user:secret@192.168.1.72:554/live/ch00_0",
        "rtspTransport": "udp",
    })
    assert secret.transport == "udp"
    assert "secret" not in secret.log_target
    assert "secret" not in redact_rtsp("ffmpeg error rtsp://user:secret@host/live")
    with pytest.raises(ValueError):
        parse_camera_config({"rtspUrl": "http://192.168.1.72/snap.jpg"})
    with pytest.raises(ValueError):
        parse_camera_config({"rtspUrl": CAMERA_URL, "archivePath": "relative/cam"})
    with pytest.raises(ValueError):
        parse_camera_config({"rtspUrl": CAMERA_URL, "retentionHours": 0})


def test_segments_cover_moment_and_period(tmp_path):
    (tmp_path / "100.ts").write_bytes(b"a")
    (tmp_path / "110.ts").write_bytes(b"b")
    (tmp_path / "note.txt").write_text("no", encoding="utf-8")
    now_us = 130 * 1_000_000
    segments = list_segments(tmp_path, segment_seconds_value=10, now_us=now_us)
    assert [segment.start_us for segment in segments] == [100_000_000, 110_000_000]
    assert segments[0].end_us == 110_000_000
    assert segments[1].end_us == now_us
    assert segment_at(segments, 105_000_000).path.name == "100.ts"
    hit = segment_at(segments, 100_000_000)
    assert hit is not None and hit.path.name == "100.ts"
    chosen = segments_overlapping(segments, 105_000_000, 115_000_000)
    assert [item.path.name for item in chosen] == ["100.ts", "110.ts"]
    assert segment_at(segments, 90_000_000) is None


def test_session_ffmpeg_uses_one_rtsp_input(tmp_path):
    camera = parse_camera_config({"rtspUrl": CAMERA_URL})
    args = session_ffmpeg_args(camera, tmp_path, 10, ffmpeg="ffmpeg")
    assert args[args.index("-rtsp_transport") + 1] == "tcp"
    assert args.count(CAMERA_URL) == 1
    assert args.count("-i") == 1
    assert "mpjpeg" in args
    assert "segment" in args
    assert "+genpts" in args
    assert "libx264" in args
    assert "copy" not in args
    assert "fps=8,scale=960:-2" in args
    preview = args.index("fps=8,scale=960:-2")
    archive = args[:preview]
    assert "scale=" not in " ".join(archive)
    assert "fps=" not in " ".join(archive)
    assert args[-1] == "pipe:1"
    assert str(tmp_path / "%s.ts") in args
    concat = tmp_path / "list.txt"
    write_concat_list(concat, [tmp_path / "100.ts"])
    assert "file '" in concat.read_text(encoding="utf-8")
    frag = fragment_ffmpeg_args(concat, tmp_path / "out.mp4", 1.5, 10, ffmpeg="ffmpeg")
    assert "libx264" in frag
    assert frag[-1].endswith("out.mp4")
    shot = snapshot_file_args(tmp_path / "100.ts", 12.5, ffmpeg="ffmpeg")
    assert shot.index("-i") < shot.index("-ss")
    assert shot[shot.index("-ss") + 1] == "12.500"
    assert "yuvj420p" in shot


def test_archive_size_and_rate_come_from_the_connector(tmp_path):
    camera = parse_camera_config({
        "rtspUrl": CAMERA_URL,
        "archiveWidth": 640,
        "archiveFps": 12,
    })
    assert camera.archive_width == 640
    assert camera.archive_fps == 12
    args = session_ffmpeg_args(camera, tmp_path, 10, ffmpeg="ffmpeg")
    preview = args.index("fps=8,scale=960:-2")
    assert args[args.index("-vf")] == "-vf"
    assert "fps=12,scale=640:-2" in args[:preview]
    native = parse_camera_config({"rtspUrl": CAMERA_URL})
    assert native.archive_width is None
    assert native.archive_fps is None
    with pytest.raises(ValueError):
        parse_camera_config({"rtspUrl": CAMERA_URL, "archiveWidth": 641})
    with pytest.raises(ValueError):
        parse_camera_config({"rtspUrl": CAMERA_URL, "archiveFps": 0})


class _Hierarchy:
    def __init__(self, by_id, connectors, links):
        self.by_id = by_id
        self.connectors = connectors
        self.links = links

    async def search(self, payload):
        if payload.get("id"):
            tag_id = payload["id"]
            if isinstance(tag_id, list):
                tag_id = tag_id[0]
            return self.by_id.get(tag_id, [])
        if payload.get("base") == "cn=connectors,cn=prs":
            return self.connectors
        return self.links.get(payload.get("base"), [])


def _app(hierarchy):
    return SimpleNamespace(
        _hierarchy=hierarchy,
        _logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        _config=SimpleNamespace(svc_name="tags_app_api", hierarchy={"class": "prsTag"}),
    )


def _video_tag(active="TRUE"):
    return [(TAG, "dn", {"prsValueTypeCode": ["6"], "prsActive": [active]})]


def _camera_connector():
    return [(
        CONN,
        "dn",
        {
            "prsEntityTypeCode": ["10"],
            "prsActive": ["TRUE"],
            "prsJsonConfigString": ['{"rtspUrl": "rtsp://192.168.1.72:554/live/ch00_0"}'],
        },
    )]


def test_ordinary_tag_is_not_a_video_response():
    hierarchy = _Hierarchy(
        {TAG: [(TAG, "dn", {"prsValueTypeCode": ["1"], "prsActive": ["TRUE"]})]},
        [],
        {},
    )
    payload = DataGet.model_validate({"tagId": TAG})
    assert asyncio.run(resolve_video_get(hierarchy, payload)) is None
    assert asyncio.run(maybe_video_data_response(_app(hierarchy), payload)) is None


def test_api_without_ldap_connects_hierarchy_before_camera_lookup(monkeypatch):
    from src.services.video import http_response

    hierarchy = _Hierarchy({TAG: _video_tag()}, [], {})
    app = SimpleNamespace(
        _logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        _config=SimpleNamespace(svc_name="tags_app_api", hierarchy={"class": "prsTag"}),
    )

    async def connect():
        return hierarchy

    monkeypatch.setattr(http_response, "_connect_video_hierarchy", connect)
    payload = DataGet.model_validate({"tagId": TAG})
    response = asyncio.run(maybe_video_data_response(app, payload))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 424
    assert app._hierarchy is hierarchy


def test_video_tag_without_camera_returns_424():
    hierarchy = _Hierarchy({TAG: _video_tag()}, [], {})
    payload = DataGet.model_validate({"tagId": TAG})
    response = asyncio.run(maybe_video_data_response(_app(hierarchy), payload))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 424


def test_video_tag_with_timestep_returns_422():
    hierarchy = _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    payload = DataGet.model_validate({"tagId": TAG, "timeStep": 1_000_000})
    response = asyncio.run(maybe_video_data_response(_app(hierarchy), payload))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422


def test_disabled_video_tag_returns_409():
    hierarchy = _Hierarchy(
        {TAG: _video_tag("FALSE")},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    payload = DataGet.model_validate({"tagId": TAG, "finish": 1_000_000})
    response = asyncio.run(maybe_video_data_response(_app(hierarchy), payload))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 409


def test_two_tags_are_rejected_when_one_is_video():
    hierarchy = _Hierarchy(
        {
            TAG: _video_tag(),
            OTHER: [(OTHER, "dn", {"prsValueTypeCode": ["1"], "prsActive": ["TRUE"]})],
        },
        [],
        {},
    )
    payload = DataGet.model_validate({"tagId": [TAG, OTHER]})
    response = asyncio.run(maybe_video_data_response(_app(hierarchy), payload))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422


def test_bound_camera_snapshot_mode_is_resolved():
    hierarchy = _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    payload = DataGet.model_validate({"tagId": TAG, "finish": 5_000_000})
    binding = asyncio.run(resolve_video_get(hierarchy, payload))
    assert binding.mode == "snapshot"
    assert binding.connector_id == CONN
    assert binding.camera.rtsp_url == CAMERA_URL
    assert binding.finish_us == 5_000_000
    live = DataGet.model_validate({"tagId": TAG})
    assert asyncio.run(resolve_video_get(hierarchy, live)).mode == "live"


def test_archive_config_uses_storage_json_and_rejects_bad_values(monkeypatch):
    from src.services.video.archive_config import parse_archive_config, reset_archive_config

    monkeypatch.setenv("VIDEO_ARCHIVE_DIR", "/var/lib/peresvet/video")
    monkeypatch.setenv("VIDEO_ARCHIVE_HOURS", "24")
    reset_archive_config()
    cfg = parse_archive_config({
        "path": "/var/lib/peresvet/video",
        "retentionHours": 48,
        "segmentSeconds": 5,
    })
    assert str(cfg.path) == "/var/lib/peresvet/video"
    assert cfg.retention_hours == 48
    assert cfg.segment_seconds == 5
    with pytest.raises(ValueError):
        parse_archive_config({"path": "relative/video", "retentionHours": 1})
    with pytest.raises(ValueError):
        parse_archive_config({"retentionHours": 0})
    empty = parse_archive_config({})
    assert empty.retention_hours == 24


def test_video_query_keeps_finish_only_when_client_sent_it():
    from starlette.requests import Request

    from src.services.video.query import payload_from_request

    request = Request({
        "type": "http",
        "query_string": f"tagId={TAG}&finish=5000000".encode(),
        "headers": [],
    })
    payload = payload_from_request(request)
    assert payload.tagId == [TAG]
    assert "finish" in payload.model_fields_set
    assert "start" not in payload.model_fields_set
    live = Request({
        "type": "http",
        "query_string": f"tagId={TAG}".encode(),
        "headers": [],
    })
    assert "finish" not in payload_from_request(live).model_fields_set


def test_platform_proxies_video_tag_when_video_server_is_configured(monkeypatch):
    from starlette.responses import JSONResponse as JR

    from src.services.video import http_response

    hierarchy = _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    monkeypatch.setenv("VIDEO_SERVER_URL", "http://video:8090")
    called = {}

    async def fake_proxy(request):
        called["query"] = request.url.query
        return JR({"proxied": True}, status_code=200)

    monkeypatch.setattr(http_response, "proxy_video_get", fake_proxy)
    request = SimpleNamespace(url=SimpleNamespace(query=f"tagId={TAG}"))
    response = asyncio.run(
        http_response.maybe_video_data_response(_app(hierarchy), DataGet.model_validate({"tagId": TAG}), request)
    )
    assert called["query"] == f"tagId={TAG}"
    assert isinstance(response, JR)
    assert response.status_code == 200


def test_connector_attributes_reject_inactive_and_keep_retention():
    from src.services.video.camera import camera_from_connector_attributes

    camera = camera_from_connector_attributes({
        "prsActive": ["TRUE"],
        "prsJsonConfigString": [json.dumps({
            "rtspUrl": CAMERA_URL,
            "archivePath": "/var/lib/peresvet/video/rear-cam",
            "retentionHours": 4,
        })],
    })
    assert camera is not None
    assert camera.retention_hours == 4
    assert camera_from_connector_attributes({
        "prsActive": ["FALSE"],
        "prsJsonConfigString": ['{"rtspUrl": "rtsp://192.168.1.72/live"}'],
    }) is None
    assert camera_from_connector_attributes({
        "prsActive": [b"TRUE"],
        "prsJsonConfigString": [b"{}"],
    }) is None


def test_retention_change_prunes_without_second_rtsp(monkeypatch, tmp_path):
    from src.services.video import runtime
    from src.services.video.runtime import CameraSession

    archive = tmp_path / "rear-cam"
    old = parse_camera_config({
        "rtspUrl": CAMERA_URL,
        "archivePath": str(archive),
        "retentionHours": 24,
    })
    session = CameraSession(CONN, old, old.segment_dir(CONN))
    session._proc = SimpleNamespace(returncode=None)
    runtime._sessions[CONN] = session
    opened = []
    pruned = []
    monkeypatch.setattr(runtime, "ensure_session", lambda *args, **kwargs: opened.append(args))
    monkeypatch.setattr(
        runtime,
        "prune_archive",
        lambda directory, keep_seconds, now_sec=None: pruned.append(keep_seconds),
    )
    try:
        newer = parse_camera_config({
            "rtspUrl": CAMERA_URL,
            "archivePath": str(archive),
            "retentionHours": 4,
        })
        assert runtime.sync_session(CONN, newer) == "retention"
        assert session.camera.retention_hours == 4
        assert pruned == [4 * 3600]
        assert opened == []
    finally:
        runtime._sessions.pop(CONN, None)


def test_stream_change_reopens_session(monkeypatch, tmp_path):
    from src.services.video import runtime
    from src.services.video.runtime import CameraSession

    archive = tmp_path / "rear-cam"
    old = parse_camera_config({
        "rtspUrl": CAMERA_URL,
        "archivePath": str(archive),
        "retentionHours": 4,
    })
    session = CameraSession(CONN, old, old.segment_dir(CONN))
    session._proc = SimpleNamespace(returncode=None)
    runtime._sessions[CONN] = session
    opened = []
    monkeypatch.setattr(runtime, "ensure_session", lambda *args, **kwargs: opened.append(args[0]))
    try:
        moved = parse_camera_config({
            "rtspUrl": "rtsp://192.168.1.73:554/live/ch00_0",
            "archivePath": str(archive),
            "retentionHours": 4,
        })
        assert runtime.sync_session(CONN, moved) == "restart"
        assert opened == [CONN]
        opened.clear()
        narrower = parse_camera_config({
            "rtspUrl": CAMERA_URL,
            "archivePath": str(archive),
            "retentionHours": 4,
            "archiveWidth": 640,
            "archiveFps": 10,
        })
        assert runtime.sync_session(CONN, narrower) == "restart"
        assert opened == [CONN]
    finally:
        runtime._sessions.pop(CONN, None)


def test_video_app_subscribes_to_connector_changes():
    from src.common.app_svc import AppSvc
    from src.services.video.video_app_settings import VideoAppSettings
    from src.services.video.video_app_svc import VideoApp

    assert "_set_handlers" not in VideoApp.__dict__
    app = object.__new__(VideoApp)
    app._handlers = {}
    app._config = VideoAppSettings()
    AppSvc._set_handlers(app)
    assert app._handlers["prsConnector.model.created"].__func__ is VideoApp._created
    assert app._handlers["prsConnector.model.updated.*"].__func__ is VideoApp._updated
    assert app._handlers["prsConnector.model.deleted.*"].__func__ is VideoApp._deleted
    result = asyncio.run(app._may_update({"id": CONN}))
    assert result == {"response": True}


def test_connector_updated_message_applies_retention(monkeypatch):
    from src.services.video import video_app_svc

    synced = []

    async def search(payload):
        assert payload["id"] == [CONN]
        return [(
            CONN,
            "dn",
            {
                "prsActive": ["TRUE"],
                "prsJsonConfigString": [json.dumps({
                    "rtspUrl": CAMERA_URL,
                    "archivePath": "/var/lib/peresvet/video/rear-cam",
                    "retentionHours": 4,
                })],
            },
        )]

    def sync_session(conn_id, camera, directory=None):
        synced.append((conn_id, camera.retention_hours))
        return "retention"

    monkeypatch.setattr(video_app_svc, "sync_session", sync_session)
    svc = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(svc_name="video_app"),
        _logger=_Logger(),
    )
    svc._apply_connector = video_app_svc.VideoApp._apply_connector.__get__(svc, SimpleNamespace)
    svc._created = video_app_svc.VideoApp._created.__get__(svc, SimpleNamespace)
    asyncio.run(video_app_svc.VideoApp._updated(svc, {"id": CONN}))
    assert synced == [(CONN, 4.0)]


def test_connector_deleted_message_stops_session_without_ldap(monkeypatch):
    from src.services.video import video_app_svc

    stopped = []

    async def stop_session(conn_id):
        stopped.append(conn_id)
        return True

    async def search(payload):
        raise AssertionError(payload)

    monkeypatch.setattr(video_app_svc, "stop_session", stop_session)
    svc = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(svc_name="video_app"),
        _logger=_Logger(),
    )
    asyncio.run(video_app_svc.VideoApp._deleted(svc, {"id": CONN}))
    assert stopped == [CONN]


def test_mqtt_presence_packet_uses_connector_id():
    from src.services.video.presence import hold_camera_presence, mqtt_connect_packet
    import src.services.video.presence as presence

    packet = mqtt_connect_packet(CONN, "prs", "secret", 60)
    assert packet[0] == 0x10
    assert CONN.encode() in packet
    marker = packet.index(b"MQTT")
    assert packet[marker + 4] == 4
    assert packet[marker + 5] == 0xC2
    presence._settings = None
    hold_camera_presence(CONN)
    assert CONN not in presence._tasks


def test_onvif_profile_and_move_command_stay_within_one_session():
    from src.services.video.onvif_ptz import (
        _axis,
        _move_body,
        password_digest,
        profile_token_from_profiles,
        soap_envelope,
    )

    xml = (
        '<trt:Profiles token="PROFILE_000"><tt:PTZConfiguration token="PTZCFG_000"/>'
        "</trt:Profiles>"
    )
    assert profile_token_from_profiles(xml) == "PROFILE_000"
    body = _move_body("PROFILE_000", "ContinuousMove", _axis(2), _axis(None), _axis(-3))
    assert 'x="1.0000"' in body and 'y="0.0000"' in body and 'x="-1.0000"' in body
    assert "PROFILE_000" in body
    digest = password_digest(b"nonce", "2026-10-05T00:00:00Z", "secret")
    assert digest
    envelope = soap_envelope("<GetStatus/>", "admin", "secret")
    assert "UsernameToken" in envelope and "secret" not in envelope


def test_camera_motion_track_adds_up_until_stop():
    from src.services.video.onvif_ptz import _Track

    track = _Track()
    track.begin(0.5, 0, 0)
    track.started -= 2
    track.settle(track.started + 2)
    assert track.pan == pytest.approx(1.0)
    assert track.started is None


def test_ptz_request_reaches_onvif_for_a_video_tag(monkeypatch):
    from starlette.requests import Request

    from src.services.video import ptz_http

    hierarchy = _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    seen = {}

    async def fake_perform(camera, command):
        seen["host"] = camera.onvif_host
        seen["port"] = camera.onvif_port
        seen["action"] = command["action"]
        return {"ok": True, "action": command["action"]}

    monkeypatch.setattr(ptz_http, "perform_ptz", fake_perform)
    monkeypatch.setattr(ptz_http, "video_server_url", lambda: None)
    app = _app(hierarchy)
    raw = json.dumps({"tagId": TAG, "action": "stop"}).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/v1/ptz/",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }, receive)
    response = asyncio.run(ptz_http.ptz_response(app, request))
    assert response.status_code == 200
    assert seen == {"host": "192.168.1.72", "port": 8899, "action": "stop"}


_IMAGING_SETTINGS = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:tt="http://www.onvif.org/ver10/schema"
 xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl"><s:Body>
<timg:GetImagingSettingsResponse><timg:ImagingSettings>
<tt:BacklightCompensation><tt:Mode>OFF</tt:Mode><tt:Level>10.0</tt:Level></tt:BacklightCompensation>
<tt:Brightness>50.0</tt:Brightness>
<tt:ColorSaturation>40.0</tt:ColorSaturation>
<tt:Contrast>60.0</tt:Contrast>
<tt:IrCutFilter>AUTO</tt:IrCutFilter>
<tt:Sharpness>30.0</tt:Sharpness>
<tt:WideDynamicRange><tt:Mode>ON</tt:Mode><tt:Level>50.0</tt:Level></tt:WideDynamicRange>
<tt:WhiteBalance><tt:Mode>MANUAL</tt:Mode></tt:WhiteBalance>
</timg:ImagingSettings></timg:GetImagingSettingsResponse>
</s:Body></s:Envelope>"""

_IMAGING_OPTIONS = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body>
<timg:GetOptionsResponse xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl"><timg:ImagingOptions>
<tt:BacklightCompensation><tt:Mode>OFF</tt:Mode><tt:Mode>ON</tt:Mode></tt:BacklightCompensation>
<tt:Brightness><tt:Min>0.0</tt:Min><tt:Max>100.0</tt:Max></tt:Brightness>
<tt:ColorSaturation><tt:Min>0.0</tt:Min><tt:Max>100.0</tt:Max></tt:ColorSaturation>
<tt:Contrast><tt:Min>0.0</tt:Min><tt:Max>100.0</tt:Max></tt:Contrast>
<tt:IrCutFilterModes>ON</tt:IrCutFilterModes>
<tt:IrCutFilterModes>OFF</tt:IrCutFilterModes>
<tt:IrCutFilterModes>AUTO</tt:IrCutFilterModes>
<tt:Sharpness><tt:Min>0.0</tt:Min><tt:Max>100.0</tt:Max></tt:Sharpness>
<tt:WideDynamicRange><tt:Mode>ON</tt:Mode><tt:Mode>OFF</tt:Mode></tt:WideDynamicRange>
<tt:WhiteBalance><tt:Mode>AUTO</tt:Mode><tt:Mode>MANUAL</tt:Mode></tt:WhiteBalance>
</timg:ImagingOptions></timg:GetOptionsResponse>
</s:Body></s:Envelope>"""


def test_onvif_imaging_settings_round_trip_into_one_field():
    from src.services.video.onvif_ptz import (
        OnvifError,
        imaging_options_from_xml,
        imaging_settings_body,
        imaging_settings_from_xml,
    )

    settings = imaging_settings_from_xml(_IMAGING_SETTINGS)
    assert settings["brightness"] == 50
    assert settings["saturation"] == 40
    assert settings["irCut"] == "AUTO"
    assert settings["backlight"] == "OFF"
    assert settings["wideDynamicRange"] == "ON"
    assert settings["whiteBalance"] == "MANUAL"
    options = imaging_options_from_xml(_IMAGING_OPTIONS)
    assert options["brightness"] == {"min": 0.0, "max": 100.0}
    assert options["irCut"]["choices"] == ["ON", "OFF", "AUTO"]
    body = imaging_settings_body("V_SRC_000", {"brightness": 140, "irCut": "OFF"}, options)
    assert "<VideoSourceToken>V_SRC_000</VideoSourceToken>" in body
    assert "<tt:Brightness>100.0</tt:Brightness>" in body
    assert "<tt:IrCutFilter>OFF</tt:IrCutFilter>" in body
    assert "Contrast" not in body
    with pytest.raises(OnvifError):
        imaging_settings_body("V_SRC_000", {"irCut": "DAY"}, options)
    with pytest.raises(OnvifError):
        imaging_settings_body("V_SRC_000", {}, options)


def test_ptz_image_set_reaches_onvif_for_a_video_tag(monkeypatch):
    from starlette.requests import Request

    from src.services.video import ptz_http

    hierarchy = _Hierarchy(
        {TAG: _video_tag()},
        _camera_connector(),
        {CONN: [(TAG, "dn", {"cn": [TAG]})]},
    )
    seen = {}

    async def fake_perform(camera, command):
        seen["action"] = command["action"]
        seen["brightness"] = command["brightness"]
        return {"imaging": {"brightness": command["brightness"]}, "options": {}}

    monkeypatch.setattr(ptz_http, "perform_ptz", fake_perform)
    monkeypatch.setattr(ptz_http, "video_server_url", lambda: None)
    app = _app(hierarchy)
    raw = json.dumps({"tagId": TAG, "action": "image_set", "brightness": 40}).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/v1/ptz/",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }, receive)
    response = asyncio.run(ptz_http.ptz_response(app, request))
    assert response.status_code == 200
    assert seen == {"action": "image_set", "brightness": 40}


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

