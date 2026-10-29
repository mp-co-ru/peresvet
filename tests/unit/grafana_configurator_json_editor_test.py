import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261029-user-folders-v1"


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["html"], options["css"], options["onRender"]


def test_configurator_json_editor_contract():
    html, css, javascript = _parts()
    field_at = html.index('id="div-prsJsonConfigString"')
    field = html[field_at : field_at + 2200]

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert 'id="prs-json-editor-node"' in field
    assert 'id="btn-prsJsonFormat"' in field
    assert 'title="Форматировать"' in field
    assert ">Форматировать<" not in field
    assert 'id="btn-prsJsonReset"' in field
    assert 'title="Сбросить изменения"' in field
    assert 'id="prs-json-editor-node-status"' in field
    assert 'id="prs-json-editor-node-gutter"' in field
    assert 'id="prs-json-editor-node-highlight"' in field
    assert 'id="prs-json-editor-node-errorbar"' in field
    assert 'id="input-prsJsonConfigString"' in field
    assert 'prsattribute="prsJsonConfigString"' in field
    assert 'ta.addEventListener("input",function(){prsJsonEditorRefresh(ta);' in javascript
    assert 'class="form-control prs-mono" id="input-prsJsonConfigString"' not in html

    assert ".prs-json-editor-code{display:flex;align-items:stretch;height:16rem" in css
    assert ".prs-json-editor-input{position:relative" in css
    assert "color:#243236;-webkit-text-fill-color:#243236" in css
    assert ".prs-json-editor-highlight{display:none}" in css
    assert "prsJsonEditorFit=function" in javascript
    assert ".prs-json-str{color:#235a66}" in css
    assert ".prs-json-editor.is-invalid{box-shadow:inset 0 0 0 2px #a34a28}" in css
    assert ".prs-json-editor-gutter{position:sticky;left:0" in css
    assert ".prs-json-error-bar{position:absolute" in css
    assert ".prs-json-line{display:block" not in css

    assert "/*prsJsonEditorStart*/" in javascript
    assert "/*prsJsonEditorEnd*/" in javascript
    assert "prsJsonEditorReset=function" in javascript
    assert "prsJsonEditorPlaceGutter=function" in javascript
    assert "if(prsJsonEditorBlockSave())return;" in javascript
    assert "window.prsJsonEditorOnInput=function" in javascript


def test_configurator_json_editor_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_json_editor_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
