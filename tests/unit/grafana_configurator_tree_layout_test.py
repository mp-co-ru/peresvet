import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["css"], options["onRender"]


def test_hierarchy_pane_fills_panel_and_scrolls_inside_the_tree():
    css, javascript = _parts()

    assert 'prsConfiguratorCodeVersion="20261102-catalog-params-read-v1"' in javascript
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
    assert "#tree.bstreeview>.prs-hierarchy-search{margin-left:0;margin-right:0}" in css
    assert "margin-left:-.6rem;margin-right:-.6rem" not in css
    assert ".prs-hierarchy-search-clear{border:0!important;background:transparent!important;color:#5a6d72!important;width:.711rem;height:.711rem;" in css
    assert (
        ".main-container .prs-hierarchy-search-clear.btn.btn-sm i.fa-solid{font-size:calc(1.1 * var(--prs-font-base) / 1.5)!important;"
        in css
    )


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


def test_connector_linked_tags_indent_past_the_connector_icon():
    css, _javascript = _parts()

    # У привязанного тега нет шеврона, поэтому иконка совпадала с иконкой коннектора.
    # Сдвиг равен колонке шеврона: 0.82em при font-size .95 * --prs-font-base и margin-right 2px.
    assert (
        "#tree.bstreeview .list-group-item.prs-connector-linked-tag[role=treeitem]"
        "{padding-left:calc(.82 * .95 * var(--prs-font-base) + 2px)!important}"
        in css
    )


def test_data_storage_linked_tags_indent_past_the_storage_icon():
    css, javascript = _parts()

    # У привязанного тега нет шеврона, поэтому иконка совпадала с иконкой хранилища.
    # Группа получает шаг уровня, строка — ширину колонки шеврона.
    assert 'n.classList.add("prs-ds-linked-group")' in javascript
    assert (
        "#tree.bstreeview .prs-ds-linked-group"
        "{margin-left:0!important;padding-left:var(--prs-tree-level-step,1.75rem)!important}"
        in css
    )
    assert (
        "#tree.bstreeview .list-group-item.prs-data-storage[role=treeitem]+.list-group[role=group]"
        "{margin-left:0!important;padding-left:var(--prs-tree-level-step,1.75rem)!important}"
        in css
    )
    assert (
        "#tree.bstreeview .list-group-item.prs-ds-linked[role=treeitem]"
        "{padding-left:calc(.82em + 2px)!important}"
        in css
    )


def test_type_icon_is_the_anchor_for_other_tree_icons():
    css, javascript = _parts()

    # Problem marks sit in the row, immediately before the node menu.
    # They do not occupy space to the left of the type icon.
    assert "prsTreePadToTypeIcon=function(pad,parentRight,childLeft,gap)" in javascript
    assert "prsTreeRollupLeft=function" not in javascript
    assert "prsTreeRestorePad=function" not in javascript
    assert 'e.insertBefore(i,menu||c||a)' in javascript
    assert 'item.insertBefore(strip,menu)' in javascript
    assert "prsLayoutTreeFromTypeIcon=function(fromFrame)" in javascript
    assert 'group.style.setProperty("padding-left",next+"px","important")' in javascript
    assert "prsLayoutTreeFromTypeIcon()}" in javascript
    assert "prsLayoutTreeFromTypeIcon()}}" in javascript
    assert (
        "#tree .list-group-item[role=treeitem]>.prs-tree-rollup-strip:not(.prs-tree-rollup-strip--spacer)"
        "{position:static;margin:0 .2rem 0 .35rem;top:auto;left:auto;right:auto;transform:none;z-index:auto;flex:0 0 auto}"
        in css
    )
    assert "#tree .list-group-item[role=treeitem]{overflow:visible}" in css
    assert "#tree .list-group[role=group]{overflow:visible}" in css

    node = shutil.which("node")
    assert node, "Node.js is required to check type-icon anchor math"
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_tree_icon_anchor_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_node_tooltip_is_description_and_errors_stay_on_icons():
    _, javascript = _parts()

    assert "function prsLdapDescription(attrs)" in javascript
    assert '["cn","objectClass","prsIndex","prsDefault","description"]' in javascript
    assert 'itemDiv.setAttribute("data-prs-description",String(t.description))' in javascript
    assert 'e.getAttribute("data-prs-description")' in javascript
    assert 'm?m+" · "+v' not in javascript
    assert 'o.title="В поддереве есть неактивные узлы (или узел неактивен)"' in javascript
    assert 's.title="Есть теги или тревоги без привязки к хранилищу"' in javascript
    assert 'l.title="Есть теги без коннектора и дочернего метода — данные не поступают"' in javascript


def test_tag_icon_color_follows_child_method_kind():
    css, javascript = _parts()

    assert 'r.append("attributes","prsEntityTypeCode")' in javascript
    assert "var r={any:{},calc:{},virt:{}}" in javascript
    assert "1===R(e)?r.virt[id]=!0:r.calc[id]=!0" in javascript
    assert "tagCalcMethod:methodCalc,tagVirtMethod:methodVirt" in javascript
    assert 't.classList.add("prs-tag-method-"+prsTagKind)' in javascript
    assert "prs-tag-tree-unlinked>.item-icon{color:var(--ioterra-rust" not in css
    assert "#tree .list-group-item.prsTag.prs-tag-method-plain>.item-icon{color:#0e9f4a!important}" in css
    assert "#tree .list-group-item.prsTag.prs-tag-method-calc>.item-icon{color:#e06a00!important}" in css
    assert "#tree .list-group-item.prsTag.prs-tag-method-virt>.item-icon{color:#9b2fd0!important}" in css
    # Проблема самого тега — отдельный значок рядом с ярлыком, со своим тултипом.
    assert "function prsTreeSetOwnMarks(item,marks)" in javascript
    assert 'anchor=active||icon;anchor?anchor.insertAdjacentElement("afterend",box)' in javascript
    assert "#tree .list-group-item[role=treeitem]>.prs-node-own-marks .prs-tree-rollup-dot{background:rgba(255,192,203,.72);" in css
    assert 'prsOwnMarks.push({kind:"storage",title:"Нет привязки к хранилищу данных"})' in javascript
    assert 'prsOwnMarks.push({kind:"nods",title:"Нет привязки к коннектору и нет дочернего метода — данные не поступают"})' in javascript
    assert "prs-tag-tree-unlinked .prs-tree-label::before" not in css
    assert 'e.insertBefore(i,menu||c||a)' in javascript


def test_data_storage_group_stays_visible_after_expand():
    _, javascript = _parts()

    assert "prsRevealTreeNode=function(el)" in javascript
    assert 'a.classList.add("show"),a.classList.remove("d-none"),queueMicrotask(function(){a.classList.add("show"),prsRevealTreeNode(a)})' in javascript
    assert "prsRevealTreeNode(a)" in javascript
