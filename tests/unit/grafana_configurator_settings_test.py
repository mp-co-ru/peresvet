import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261030-font-apply-v1"


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
    assert 'id="input-prsFontSize"' in dialog
    assert "Размер шрифта" in dialog
    assert dialog.index("chk-sortNodesAlphabetically") < dialog.index("input-prsFontSize")

    assert ".prs-tree-header{display:flex" in css
    assert ".prs-settings-btn{margin-left:auto" in css
    assert ".prs-settings-overlay.is-open{display:flex}" in css

    assert "prs.configurator.autoLinkTagDefault" in javascript
    assert 'if(202===e.status){pe();var prsCur=n("div.currentNode")[0];prsCur&&String(prsCur.id)===String(t.id)&&me(t.id)}' in javascript
    assert "prs.configurator.sortNodesAlphabetically" in javascript
    assert "prsNodesSortedByName=function()" in javascript
    assert 'localeCompare(i,"ru",{numeric:!0,sensitivity:"base"})' in javascript
    assert '"prsObject"===t?0:"prsTag"===t?1:"prsAlert"===t?2' in javascript
    assert "prsResortVisibleTree=function()" in javascript
    assert 'e.querySelectorAll(\'#tree [role="group"]\')' in javascript
    assert "data-prs-platform-order" in javascript
    assert "prsLoadedGroup&&prsNodesSortedByName()&&sortList(prsLoadedGroup)" in javascript
    assert "prsNodesSortedByName()&&sortList(groupItems)" in javascript
    assert "prs.configurator.fontSize" in javascript
    assert "prsFontBasePx=function(raw)" in javascript
    assert "prsApplyFontBase=function(raw,persist)" in javascript
    assert 't.querySelectorAll(".prs-split-root").forEach(add)' in javascript
    assert 'node.style.setProperty("--prs-font-base",px)' in javascript
    assert '__prsConfiguratorGetEl("input-prsFontSize")' in javascript
    assert "--prs-font-base:16px" in css
    assert ".prs-split-root{--prs-font-base:16px;font-size:var(--prs-font-base)}" in css
    assert "font-size:calc(.8125 * var(--prs-font-base))" in css
    assert "font:400 calc(.8125 * var(--prs-font-base))/1.45" in css
    assert "font-size:11px" not in html
    assert "font-size:.875rem" not in css


def _tab_content_depth(html: str, marker: str) -> int:
    import re

    start = html.index('<div class="tab-content" id="prs-form-tab-content">')
    at = html.index(marker)
    depth = 0
    for match in re.finditer(r"<div\b[^>]*>|</div>", html[start:at]):
        depth += -1 if match.group(0).startswith("</") else 1
    return depth


def test_configurator_connector_binding_labels():
    html, _css, javascript = _parts()
    pane_at = html.index('id="prs-tab-pane-connector"')
    # Вкладка «Коннектор» лежит внутри переключателя вкладок, а не под «Свойствами».
    assert _tab_content_depth(html, 'id="prs-tab-pane-connector"') == 1
    assert _tab_content_depth(html, 'id="prs-storage-alert-only"') == 2
    pane = html[pane_at : pane_at + 1800]
    assert ">Описание <" in pane
    assert ">Конфигурация</label>" in pane
    assert "Описание привязки" not in html
    assert "Конфигурация привязки" not in html
    assert "Конфигурация привязки" not in javascript
    assert '"Конфигурация: "' in javascript


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


def test_configurator_font_base_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_font_base_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
