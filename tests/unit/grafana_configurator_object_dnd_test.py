import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"


def _dashboard_parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return dashboard, options["css"], options["onRender"]


def test_object_tree_dnd_dashboard_contract():
    dashboard, css, javascript = _dashboard_parts()

    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert (
        'prsConfiguratorCodeVersion="20261009-services-splitter-v6"' in javascript
    )
    for required_fragment in (
        "prsBindAllObjectTreeDnd",
        "prsTreeBindObjectDnd",
        "prsTreeMoveObjectRows",
        "prsTreeMultiHandleClick",
        "prsTreeDraggedTopRows",
        "prsTreeClearObjectMultiSelect",
        'objectClass="prsObject"',
        "parentId:t.id",
        'if("function"==typeof prsTreeMultiHandleClick&&prsTreeMultiHandleClick(t,e,r,n))return',
        '"function"==typeof prsTreeBindObjectDnd&&prsTreeBindObjectDnd(itemDiv)',
        'var s=e.querySelector(":scope > .prs-tree-label");s?e.insertBefore(a,s):n.insertAdjacentElement("afterend",a)',
        ':scope > .prs-node-actions > .prs-tree-active-btn',
        '"prsTag"===r&&"tags"!==n',
        'Ce[e.getAttribute("objectClass")]',
        "prsTreeSetNodeTitle",
        '[objectClass="prsTag"]',
    ):
        assert required_fragment in javascript

    for required_rule in (
        "prs-tree-selected",
        "prs-tree-drop-target",
        "prs-tree-dnd-moving",
    ):
        assert required_rule in css
        assert required_rule in javascript

    assert "inset 3px 0 0" not in css
    assert "#cde3e8" in css
    assert "currentNode::after" not in css
    assert "prs-tree-selected::after" not in css
    assert (
        '["objects","fa-object-group","Новый объект"],["tags","fa-tag","Новый тег"]'
        in javascript
    )
    assert (
        '["__copy__","fa-clone","Копировать"],["__sep__","after-copy"],'
        '["__active__","fa-pause","Приостановить узел"],'
        '["__sep__","after-active"],["__delete__","fa-trash-can","Удалить узел"]'
        in javascript
    )
    assert "prsConfirmAction" in javascript
    assert 'fill="#f5c518"' in javascript
    assert 'createElement("span");a.className="prs-tree-active-btn"' in javascript
    assert 'addEventListener("click",oe)' not in javascript
    assert 'confirm("Вы уверены, что хотите удалить этот узел?")' not in javascript
    assert "window.confirm" not in javascript
    assert '!confirm(' not in javascript
    assert 'prsConfirmAction("Копировать узел?"' in javascript
    assert 'prsConfirmAction("Экспорт CSV"' in javascript
    assert "prs-node-menu-sep" in css
    assert "prs-confirm-overlay" in css
    assert "prsClearRightPane=function()" in javascript
    assert 'c&&s[c]&&"function"==typeof prsClearRightPane&&prsClearRightPane()' in javascript
