import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261004-video-toggle-v1"


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["html"], options["css"], options["onRender"]


def test_configurator_settings_dialog_contract():
    html, css, javascript = _parts()
    header_at = html.index('class="p-2 sub-element prs-tree-header"')
    header = html[header_at : header_at + 1200]
    dialog_at = html.index('id="prs-settings-overlay"')
    dialog = html[dialog_at : dialog_at + 1600]

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "Пересвет" in header
    assert header.index("Пересвет") < header.index('id="button-prsSettings"')
    assert 'aria-label="Настройки"' in header
    assert 'class="prs-settings-icon"' in header
    assert "prs-auto-link-wrap" not in html
    assert html.count('id="chk-autoLinkTagDefault"') == 1
    assert 'id="chk-autoLinkTagDefault"' in dialog
    assert 'id="chk-sortNodesAlphabetically"' in dialog
    assert "Привязка тегов и тревог к хранилищу по умолчанию при создании" in dialog
    assert "Сортировка узлов по алфавиту" in dialog
    assert dialog.index("chk-autoLinkTagDefault") < dialog.index("chk-sortNodesAlphabetically")

    assert ".prs-tree-header{display:flex" in css
    assert ".prs-settings-btn{margin-left:auto" in css
    assert ".prs-settings-overlay.is-open{display:flex}" in css

    assert "prs.configurator.autoLinkTagDefault" in javascript
    assert "prs.configurator.sortNodesAlphabetically" in javascript
    assert "prsNodesSortedByName=function()" in javascript
    assert 'localeCompare(i,"ru",{numeric:!0,sensitivity:"base"})' in javascript
    assert '"prsObject"===t?0:"prsTag"===t?1:"prsAlert"===t?2' in javascript
    assert "prsResortVisibleTree=function()" in javascript
    assert 'e.querySelectorAll(\'#tree [role="group"]\')' in javascript
    assert "data-prs-platform-order" in javascript
    assert "prsLoadedGroup&&prsNodesSortedByName()&&sortList(prsLoadedGroup)" in javascript
    assert "prsNodesSortedByName()&&sortList(groupItems)" in javascript


def test_configurator_settings_sort_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_settings_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
