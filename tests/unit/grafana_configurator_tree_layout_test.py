import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["css"], options["onRender"]


def test_hierarchy_pane_fills_panel_and_scrolls_inside_the_tree():
    css, javascript = _parts()

    assert 'prsConfiguratorCodeVersion="20261009-camera-audio-v1"' in javascript
    assert 'rgba(44,112,127,.1), rgba(44,112,127,.32) 48%, rgba(44,112,127,.1)' in javascript
    assert 'rgba(44,112,127,.72)' not in javascript
    assert 'rgba(44,112,127,.32) 48%,rgba(44,112,127,.1)' in css
    assert "min-height:min(88vh,920px)" not in css
    assert (
        ".main-container.prs-split-root{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important}"
        in css
    )
    assert (
        ".prs-tree-scroll{display:flex!important;flex-direction:column!important;flex:1 1 auto!important;min-height:0!important;overflow:hidden!important}"
        in css
    )
    assert "#tree.bstreeview{flex:1 1 auto!important;min-height:0!important;" in css
    assert "overflow:auto!important}" in css.split("#tree.bstreeview{flex:1 1 auto!important;")[1][:220]
    assert (
        "#tree.bstreeview>.list-group[role=group].show{display:block!important;flex:0 0 auto!important;height:auto!important;min-height:min-content!important;overflow:visible!important}"
        in css
    )
    assert "#tree .prs-hierarchy-search{position:sticky;top:0;z-index:6;background:var(--prs-bg,#fff)}" in css


def test_node_menu_is_positioned_outside_the_clipped_tree():
    css, javascript = _parts()

    assert ".prs-node-actions.is-open .prs-node-menu{position:fixed!important;" in css
    assert "prsPositionTreeActionMenu=function(actions)" in javascript
    assert "prsPositionTreeActionMenu(t)" in javascript
    assert 'addEventListener("scroll",function(){prsCloseTreeActionMenus()},!0)' in javascript


def test_services_splitter_sits_between_hierarchy_and_services():
    css, javascript = _parts()
    html = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["html"]
    tree_at = html.index('class="p-2 mt-2 prs-tree-scroll"')
    split_at = html.index('id="prs-splitter-services"')
    services_at = html.index('class="p-2 mt-2 prs-services-tree-scroll"')
    assert tree_at < split_at < services_at
    assert 'aria-orientation="horizontal"' in html[split_at - 120 : split_at + 280]
    assert 'class="prs-splitter prs-splitter-h"' in html
    assert "prs-splitter-grip" not in html
    assert "prs-splitter-grip" not in css
    assert "prsInitServicesSplitter=function()" in javascript
    assert "prsInitServicesSplitter()" in javascript
    assert 'setProperty(name,val,"important")' in javascript
    assert 'imp(bar,"cursor","row-resize")' in javascript
    assert 'imp(bar,"height","8px")' in javascript
    assert "prsSplitServicesRatio" in javascript
    assert "left.insertBefore(bar,services)" in javascript
    assert "#prs-splitter-services{flex:0 0 8px!important;" in css
    assert "cursor:row-resize!important" in css
    assert "cursor:row-resize" in css
    assert "#prs-split-left .prs-services-tree-scroll{flex:0 0 var(--prs-services-size,auto)!important;" in css


def test_data_storage_group_stays_visible_after_expand():
    _, javascript = _parts()

    assert "prsRevealTreeNode=function(el)" in javascript
    assert 'a.classList.add("show"),a.classList.remove("d-none"),queueMicrotask(function(){a.classList.add("show"),prsRevealTreeNode(a)})' in javascript
    assert "prsRevealTreeNode(a)" in javascript
