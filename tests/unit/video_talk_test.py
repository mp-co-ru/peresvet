"""Разговор в камеру: свёртка пароля и кадр G.711, без второго RTSP."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.services.video.camera import parse_camera_config
from src.services.video.talk import pcma_frame, sofia_hash, talk_credentials, talk_packet

TAG = "a7b64b16-584c-1041-9006-fdeefcc48ce5"
CONN = "b459e120-584c-1041-9008-fdeefcc48ce5"


def test_rejected_login_names_the_password_and_a_lockout():
    from src.services.video.talk import talk_reject_message

    assert "onvifPassword" in talk_reject_message(203)
    assert "заблокировала" in talk_reject_message(206)
    assert talk_reject_message(0) == "Камера не приняла разговор."


def test_sofia_hash_folds_the_password_and_login_packet_omits_it():
    folded = sofia_hash("admin")
    assert folded == "6QNMIQGe"
    assert "admin" not in folded
    secret = "secret"
    packet = talk_packet(1000, json.dumps({"PassWord": sofia_hash(secret)}).encode(), 0, 0)
    assert packet[0] == 255
    assert int.from_bytes(packet[14:16], "little") == 1000
    assert secret.encode() not in packet


def test_pcma_frame_is_one_g711_block():
    frame = pcma_frame(b"\x01\x02")
    assert frame[:4] == b"\x00\x00\x01\xfa"
    assert frame[4] == 14
    assert frame[5] == 2
    assert int.from_bytes(frame[6:8], "little") == 320
    assert len(frame) == 328
    assert frame[8] == 1 and frame[9] == 2
    assert frame[-1] == 0xD5


def test_talk_credentials_come_from_the_rtsp_path_or_onvif_keys():
    from_path = parse_camera_config({
        "rtspUrl": "rtsp://192.168.1.65:554/user=admin_password=secret_channel=0_stream=0.sdp",
    })
    assert talk_credentials(from_path) == ("admin", "secret")
    from_userinfo = parse_camera_config({
        "rtspUrl": "rtsp://user:secret@192.168.1.65:554/live",
    })
    assert talk_credentials(from_userinfo) == ("user", "secret")
    preferred = parse_camera_config({
        "rtspUrl": "rtsp://192.168.1.65:554/user=admin_password=secret_channel=0_stream=0.sdp",
        "onvifUser": "admin",
        "onvifPassword": "other",
    })
    assert talk_credentials(preferred) == ("admin", "other")
    assert talk_credentials(parse_camera_config({"rtspUrl": "rtsp://192.168.1.65/live"})) is None


def test_talk_without_a_password_does_not_open_the_camera(monkeypatch):
    from src.services.video import capture_http

    async def search(payload):
        assert payload["id"] == [CONN]
        return [(
            CONN,
            "dn",
            {
                "prsActive": ["TRUE"],
                "prsJsonConfigString": [json.dumps({"rtspUrl": "rtsp://192.168.1.65/live"})],
            },
        )]

    def boom(*args, **kwargs):
        raise AssertionError("камера")

    monkeypatch.setattr(capture_http, "CameraTalk", boom)
    app = SimpleNamespace(
        _hierarchy=SimpleNamespace(search=search),
        _config=SimpleNamespace(nodes=[]),
    )
    response = asyncio.run(capture_http.capture_talk(app, CONN, None))
    assert response.status_code == 422


def test_public_talk_route_is_proxied_with_buffering_off():
    text = open(
        "config/nginx/peresvet/locations/peresvet.locations.conf.template",
        encoding="utf-8",
    ).read()
    start = text.index("location = /v1/talk/")
    block = text[start:text.index("location", start + 10)]
    assert "proxy_request_buffering off" in block
    assert "proxy_buffering off" in block
    assert "proxy_pass http://tags_app_api" in block
