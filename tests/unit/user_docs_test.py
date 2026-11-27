"""Пользовательская документация совпадает с тем, что делает платформа."""

import json
import re
import runpy
import sys
from pathlib import Path

from src.common.consts import CNDataStorageTypes, CNTagValueTypes
from src.common.tag_data_points import normalize_point_xyq


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/source"
API_PAGES = (
    "api_nodes",
    "objects",
    "tags",
    "alerts",
    "methods_api_doc",
    "connectors",
    "schedules",
    "dataStorages_api_doc",
    "folders",
    "data_api",
)


def _text(relative: str) -> str:
    return (DOCS / relative).read_text(encoding="utf-8")


def _table_row(page: str, key: str) -> str:
    """Строка list-table, которая начинается с ячейки ``key``."""
    row = page.split(f"* - ``{key}``", 1)[1]
    return re.split(r"\n\s*\* - |\n\n", row, maxsplit=1)[0]


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


def _sphinx_conf(monkeypatch, **env) -> dict:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "path", list(sys.path))
    return runpy.run_path(str(DOCS / "conf.py"))


def test_docs_release_comes_from_prs_version(monkeypatch):
    conf = _sphinx_conf(monkeypatch, PRS_VERSION="v9.9.9")
    assert conf["release"] == "v9.9.9"
    assert conf["version"] == "v9.9.9"


def test_docs_release_falls_back_to_newest_release_tag(monkeypatch):
    monkeypatch.delenv("PRS_VERSION", raising=False)
    conf = _sphinx_conf(monkeypatch)
    assert conf["release"] != "0.4"
    if conf["release"]:
        assert re.fullmatch(r"v\d+(\.\d+)*", conf["release"]) or (ROOT / "VERSION").is_file()


def test_sidebar_shows_release_under_logo():
    layout = _text("_templates/layout.html")
    assert '{% extends "!layout.html" %}' in layout
    assert layout.index('class="logo"') < layout.index("{{ release }}") < layout.index("searchbox.html")
    conf = _text("conf.py")
    assert "'display_version'" not in conf


def test_autodoc_keeps_pydantic_annotations_intact():
    assert "autodoc_use_type_comments = False" in _text("conf.py")


def test_docs_workflow_fetches_release_tags():
    workflow = (ROOT / ".github/workflows/build_sphinx_docs.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow


def test_security_docs_list_connector_service_actions():
    page = _text("security_extension_points.rst")
    for action in (
        "prsConnector.link_status_read",
        "prsConnector.connector_command_output_read",
        "prsConnector.service_inventory_read",
        "prsConnector.service_log_clear",
    ):
        assert action in page, action


def test_api_reference_is_written_by_hand_and_listed():
    api = _text("api.rst")
    for page in API_PAGES:
        assert f"<{page}>" in api, page
        assert ".. automodule::" not in _text(f"{page}.rst"), page


def test_guides_for_alerts_storages_and_schedules_are_in_main_toctree():
    index = _text("index.rst")
    for entry in (
        "Тревоги<alerts_guide>",
        "Хранилища данных<storages_guide>",
        "Расписания<schedules_guide>",
    ):
        assert entry in index, entry


def test_type_codes_in_reference_match_constants():
    value_types = _table_row(_text("tags.rst"), "prsValueTypeCode")
    for code in CNTagValueTypes:
        assert f"``{int(code)}``" in value_types, code
    storages = _text("dataStorages_api_doc.rst")
    for code in {int(item) for item in CNDataStorageTypes}:
        assert f"* - ``{code}``" in storages, code


def test_alert_defaults_in_guide_match_api():
    from src.services.alerts.api_crud.alerts_api_crud_svc import valid_alert_config

    guide = _text("alerts_guide.rst")
    for key, value in valid_alert_config({}).items():
        assert f"``{json.dumps(value)}``" in _table_row(guide, key), key


def test_schedule_defaults_in_reference_match_api():
    from src.services.schedules.api_crud.schedules_api_crud_svc import valid_schedule_config

    config = valid_schedule_config({})
    page = _text("schedules.rst")
    assert f"``{config['interval_type']}``" in _table_row(page, "interval_type")
    assert f"``{config['interval_value']}``" in _table_row(page, "interval_value")


def test_point_shapes_for_data_write_match_normalization():
    page = _text("data_api.rst")
    for shape in ("``[x, y, q]``", "``[x, y]``", "``[y]``", "``[]``"):
        assert shape in page, shape
    assert normalize_point_xyq([5, 7, 0]) == (5, 7, 0)
    assert normalize_point_xyq([5, 7]) == (5, 7, None)
    assert normalize_point_xyq([7])[1:] == (7, None)
    assert normalize_point_xyq([])[1:] == (None, None)


def test_storages_guide_says_victoriametrics_is_not_shipped():
    one_app = (ROOT / "src/services/one_app/one_app.py").read_text(encoding="utf-8")
    assert "victoria" not in one_app.lower()
    assert "в стандартную поставку не входит" in _text("storages_guide.rst")


def test_administration_describes_every_backup_script():
    page = _text("administration.rst")
    scripts = sorted((ROOT / "admin_scripts").rglob("*.sh"))
    assert scripts
    missing = [path.name for path in scripts if path.name not in page]
    assert not missing, missing
