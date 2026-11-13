"""Пользовательская документация совпадает с тем, что делает платформа."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/source"


def _text(relative: str) -> str:
    return (DOCS / relative).read_text(encoding="utf-8")


def test_methods_chapter_is_in_main_toctree_once():
    assert "Методы<methods>" in _text("index.rst")
    assert "methods.rst" not in _text("microservices.rst")


def test_video_docs_describe_webrtc_live_stream():
    guide = _text("video.rst")
    api = _text("video_tag.rst")
    for page in (guide, api):
        assert "MJPEG" not in page
    assert "/v1/video/webrtc" in api
    assert "RTCPeerConnection" in api
    assert "Живой поток открывается через WebRTC." in api
    assert "Сервис подхвата видео не запущен." in guide
    live_img = re.compile(r'<img[^>]*src="/v1/data/\?tagId=[^"&]*"')
    assert not live_img.search(guide)
    assert not live_img.search(api)


def test_installation_mirror_needs_scheme_and_no_daemon_json():
    installation = _text("installation.rst")
    assert "insecure-registries" not in installation
    assert "PRS_REGISTRY_MIRROR=http://127.0.0.1:5000" in installation
    assert "--mirror mirror.example.com:5000" not in installation


def test_mcp_page_lists_every_tool():
    server = (ROOT / "src/mcp_server/server.py").read_text(encoding="utf-8")
    tools = set(re.findall(r"@mcp\.tool\s+async def (peresvet_\w+)", server))
    assert tools
    page = _text("mcp.rst")
    missing = sorted(name for name in tools if f"``{name}``" not in page)
    assert not missing, missing


def test_security_docs_list_connector_service_actions():
    page = _text("security_extension_points.rst")
    for action in (
        "prsConnector.link_status_read",
        "prsConnector.connector_command_output_read",
        "prsConnector.service_inventory_read",
        "prsConnector.service_log_clear",
    ):
        assert action in page, action
