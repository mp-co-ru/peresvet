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


def test_storage_tag_bindings_use_tag_paths_and_a_context_menu():
    html, css, javascript = _parts()

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "prsDsTagPathLabel=function(index,tagId)" in javascript
    assert 'names.join(" → ")' in javascript
    assert "function prsVideoTagOnHistorian()" in javascript
    assert "(s||prsVideoTagOnHistorian())?be()" in javascript
    assert "3!==r.entityType" in javascript
    assert "prsDsTagOpenPath=function(index,tagId)" in javascript
    assert "prsDsTagPathLoad(!1)" in javascript
    assert 'pull("/v1/objects/",["prsObject","prsFolder","prsTag"])' in javascript
    assert 'pull("/v1/tags/",["prsTag","prsFolder"])' in javascript
    assert "label=prsDsTagPathLabel(index,tagId)||ldapCn" in javascript
    assert 'u.setAttribute("data-ds-entity-type"' in javascript
    assert 'u.setAttribute("data-prs-store"' in javascript
    assert 'addEventListener("contextmenu",function(ev)' not in javascript
    assert '["__goto_tag__","fa-arrow-right","Перейти к тегу"]' in javascript
    assert '["__unlink_tag__","fa-trash-can","Удалить"]' in javascript
    assert '("prsDsLinkedTag"===r||"prsConnectorLinkedTag"===r)?a(["__goto_tag__","__unlink_tag__"])' in javascript
    assert "label=prsDsTagPathLabel(index,r)||c" in javascript
    assert 'connId?"/v1/connectors/":"/v1/dataStorages/"' in javascript
    assert 'if("__goto_tag__"===t)return void prsDsLinkedGoToTag(r)' in javascript
    assert 'if("__unlink_tag__"===t)return void prsDsLinkedUnlinkTag(r)' in javascript
    assert '&&!e.classList.contains("prs-ds-linked")' not in javascript
    assert "prsDsLinkedGoToTag=function(row)" in javascript
    assert "prsHierarchySearchOpenPath(path)" in javascript
    assert "unlinkTags:[tagId]" in javascript
    assert 'method:"PUT"' in javascript
    assert "prsApplyDsLinkedTagParams=function(panel,link,tagId,entityType)" in javascript
    assert 'title.textContent="Параметры привязки"' in javascript
    assert 'id="prs-ds-linked-tag-params"' in html
    assert ".prs-ds-linked-tag-menu{display:none;position:fixed" in css
    assert ".prs-ds-linked-tag-menu-item-danger{color:#863c20}" in css
    assert "min-width:0!important;box-sizing:border-box!important" in css
    assert "#tree .list-group-item[role=treeitem]>.prs-tree-label,#services-tree .list-group-item[role=treeitem]>.prs-tree-label{flex:1 1 0%!important" in css
    assert "#tree .list-group-item[role=treeitem]>.prs-node-actions,#services-tree .list-group-item[role=treeitem]>.prs-node-actions{margin-left:0!important" in css


def test_storage_tag_path_helpers():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_ds_link_names_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
