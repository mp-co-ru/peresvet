"""Папка создаётся флагом folder у сущности, без отдельного /v1/folders."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_api_page_describes_folder_flag():
    page = _text("docs/source/folders.rst")
    assert "Папки<folders>" in _text("docs/source/api.rst")
    assert '"folder": true' in page
    assert "POST /v1/objects/" in page
    assert "POST /v1/tags/" in page
    assert "POST /v1/methods/" in page
    assert "/v1/methods/folders" not in page
    assert "по умолчанию" in page


def test_node_create_carries_folder_flag():
    source = _text("src/common/api_crud_svc.py")
    assert "folder: bool = Field(" in source
    model = _text("src/common/model_crud_svc.py")
    assert "mes.pop(\"folder\", False)" in model
    assert "async def _create_user_folder" in model
    nginx = _text("config/nginx/peresvet/locations/peresvet.locations.conf.template")
    assert "location = /v1/folders {" not in nginx
