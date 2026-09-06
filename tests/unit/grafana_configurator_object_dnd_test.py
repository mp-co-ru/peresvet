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
        'prsConfiguratorCodeVersion="20260906-object-tree-dnd-v1"' in javascript
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
    ):
        assert required_fragment in javascript

    for required_rule in (
        "prs-tree-selected",
        "prs-tree-drop-target",
        "prs-tree-dnd-moving",
    ):
        assert required_rule in css
        assert required_rule in javascript
