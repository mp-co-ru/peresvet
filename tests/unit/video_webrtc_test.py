"""Живой WebRTC: один поток H.264 режется на кадры, SDP указывает адрес страницы."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from src.services.video.annexb import pop_access_units
from src.services.video.camera import parse_camera_config
from src.services.video.webrtc_sdp import advertise_sdp, host_from_header


def _nal(nal_type: int, payload: bytes = b"\x00") -> bytes:
    return b"\x00\x00\x00\x01" + bytes([nal_type]) + payload


def test_access_units_split_on_the_second_aud():
    buffer = bytearray()
    first = _nal(7, b"sps") + _nal(8, b"pps") + _nal(9, b"\xf0") + _nal(5, b"idr")
    second = _nal(9, b"\xf0") + _nal(1, b"p")
    assert pop_access_units(buffer, first) == []
    units = pop_access_units(buffer, second + _nal(9, b"\xf0"))
    assert units[0].startswith(_nal(7, b"sps"))
    assert units[0].endswith(_nal(5, b"idr"))
    assert units[1].startswith(_nal(9, b"\xf0"))
    assert buffer.startswith(_nal(9, b"\xf0"))


def test_sdp_candidates_use_the_page_host():
    sdp = "\r\n".join([
        "v=0",
        "a=candidate:1 1 udp 1 10.66.0.8 8189 typ host",
        "a=candidate:2 1 tcp 1 10.66.0.8 8189 typ host tcptype passive",
        "",
    ])
    rewritten = advertise_sdp(sdp, "127.0.0.1")
    assert " udp " not in rewritten
    assert "a=candidate:2 1 tcp 1 127.0.0.1 8189 typ host tcptype passive" in rewritten
    direct = advertise_sdp(sdp, "172.16.20.61")
    assert "a=candidate:1 1 udp 1 172.16.20.61 8189 typ host" in direct
    assert rewritten.endswith("\r\n")
    assert host_from_header("127.0.0.1:8443") == "127.0.0.1"
    assert host_from_header("peresvet.local") == "peresvet.local"


def test_webrtc_opens_the_session_with_storage_settings(monkeypatch):
    from src.services.video import capture_http

    bare = parse_camera_config({"rtspUrl": "rtsp://192.168.1.72:554/live"})
    stored = replace(bare, archive_width=640, archive_fps=12)
    seen = []

    async def load(_app, _connector_id):
        return bare

    async def with_storage(_hierarchy, _connector_id, _camera):
        return stored

    async def get_session(connector_id, camera, directory=None):
        seen.append((connector_id, camera.archive_width, camera.archive_fps))

    async def answer_offer(connector_id, sdp, host):
        return {"sdp": "v=0\r\n", "type": "answer"}

    monkeypatch.setattr(capture_http, "_load_camera", load)
    monkeypatch.setattr(capture_http, "camera_for_session", with_storage)
    monkeypatch.setattr(capture_http, "get_session", get_session)
    monkeypatch.setattr(
        "src.services.video.webrtc_fanout.answer_offer",
        answer_offer,
    )
    app = SimpleNamespace(_hierarchy=object())
    response = asyncio.run(capture_http.capture_webrtc(app, "cam-1", {"sdp": "offer", "advertiseHost": "127.0.0.1"}))
    assert response.status_code == 200
    assert seen == [("cam-1", 640, 12)]
