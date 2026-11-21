import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261117-alarm-monitor-v60"
MENU_LITERAL = (
    '["__copy__","fa-clone","Копировать"],["__sep__","after-copy"],'
    '["__active__","fa-pause","Приостановить узел"],'
    '["__sep__","after-active"],["__goto_tag__","fa-arrow-right","Перейти к тегу"],'
    '["__unlink_tag__","fa-trash-can","Удалить"],["__delete__","fa-trash-can","Удалить узел"]'
)


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["css"], options["onRender"]


def _between(javascript, start_mark, end_mark):
    start = javascript.find(start_mark)
    end = javascript.find(end_mark, start + len(start_mark))
    assert start >= 0 and end > start
    return javascript[start:end]


def test_alarm_monitor_is_a_separate_tree_mark_and_uses_the_alarms_api():
    css, javascript = _parts()

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "@keyframes prs-alarm-pulse" in css
    assert "#tree .list-group-item[role=treeitem]>.prs-alarm-pulse{" in css
    assert "background:#dc3545" in css
    assert "function prsAlarmPlaceDot(row)" in javascript
    place = _between(javascript, "function prsAlarmPlaceDot", "function prsAlarmClearDot")
    assert "prs-alarm-pulse" in place
    assert 'if("prsAlert"===row.getAttribute("objectClass"))' in place
    assert 'row.querySelector(":scope > .prs-node-own-marks")' in place
    assert 'row.querySelector(":scope > .prs-tree-active-btn")' in place
    assert 'row.querySelector(":scope > .item-icon")' in place
    assert 'after.insertAdjacentElement("afterend",dot)' in place
    assert "function prsAlarmIsTreeRoot(row)" in javascript
    assert "prsTreeRootIds.indexOf(id)" in javascript
    assert "if(prsAlarmIsTreeRoot(row))" in javascript
    assert "Старт:" in javascript
    assert "Финиш:" in javascript
    assert "Квитирование:" in javascript
    assert "function prsAlarmPathLabel(dn)" in javascript
    assert 'path.className="prs-alarm-row-path"' in javascript
    assert 'kept.join("→")' in javascript
    assert "fired: " not in javascript
    assert "prs-problem-menu" not in place
    assert "prs-tree-rollup-dot" not in place
    assert "prs-problem-menu-item" not in place
    assert 'btn.title="Тревоги"' in javascript
    assert "prs-node-menu-label\">Тревоги" in javascript
    assert 'data-tb="__alarms__"' in javascript
    assert 'if("__alarms__"===t)return void prsAlarmOpenList(r)' in javascript
    assert 'prsAlarmUrl("?getChildren=true&fired=false&format=true")' in javascript
    assert "parentId" not in 'prsAlarmUrl("?getChildren=true&fired=false&format=true")'
    assert "if(!on)return void(btn&&btn.remove())" not in javascript
    assert "function prsAlarmListUrl()" in javascript
    assert "prs-alarm-key-parent" in javascript
    assert 'id=\\"prs-alarm-key-parent\\" placeholder=\\"id узла\\" disabled=\\"disabled\\"' in javascript
    assert "prs-alarm-key-fired" in javascript
    assert 'id=\\"button-alarmListKeysToggle\\"' in javascript
    assert 'data-prs-expanded=\\"0\\"' in javascript
    assert "prs-tag-get-key-label" in javascript
    assert "prs-tag-get-key-docs" in javascript
    assert "#prs-alarm-list .prs-tag-get-key-label{gap:.35rem;background-color:#e9ecef}" in css
    assert 'q.append("parentId",parentId)' in javascript
    assert 'q.append("fired","false")' in javascript
    assert 'id=\\"button-alarmListGet\\" title=\\"Читать данные\\" aria-label=\\"Читать данные\\"' in javascript
    assert "Получить данные" not in javascript
    assert "function prsAlarmListOnKey(){prsAlarmListSyncUrl()}" in javascript
    assert "function prsAlarmListLoad()" in javascript
    assert 'getBtn.addEventListener("click",function(){prsAlarmListLoad()})' in javascript
    assert "prsAlarmMonitorTick();prsAlarmListLoad()" in javascript
    assert "listReq=fetch(prsAlarmListUrl()" not in javascript
    ack = _between(javascript, "function prsAlarmAck", "function prsAlarmOpenList")
    assert 'body:JSON.stringify({id:String(id)})' in ack
    assert 'method:"PUT"' in ack
    assert "x:" not in ack
    assert '"x"' not in ack
    assert "Активна, не квитирована" in javascript
    assert "Активна, квитирована" in javascript
    assert "Пропала, не квитирована" in javascript
    assert "window.prsAlarmListOpen?3000:5000" in javascript
    assert "window.prsAlarmMonitorTimer=setInterval(function(){prsAlarmMonitorTick()},every)" in javascript
    assert "clearInterval(window.prsAlarmMonitorTimer)" in javascript
    assert "if(window.prsAlarmMonitorTimer&&window.prsAlarmMonitorEvery===every)return" in javascript
    assert MENU_LITERAL in javascript
    assert 'case"prsTag":a("tags"===n?["userFolders","tags"]:["__copy__","__active__","__delete__","alerts","methods"]);' in javascript
    assert 'case"prsAlert":a(["__copy__","methods","__active__","__delete__"]);' in javascript
    assert 'case"prsModelNode":a(["methodFolders","catalogMethods","methodDescription","__active__","__delete__"]);' in javascript
    assert "--prs-tree-rollup-strip-width:3.35rem" in css
    assert "function prsBindOwnMenu(box)" in javascript
    assert "function prsBindRollupMenu(strip)" in javascript
    assert "function prsTreeSetOwnMarks(item,marks)" in javascript
    assert "function prsMethodIdByParameter(item,byDn)" in javascript
    assert "prsAlarmCloseList();if(prsTreeRootIds.includes(n)||\"prsConnectorLinkedTag\"===r)prsFormDismiss();else fillForm(t)" in javascript


def test_alarm_state_classification_and_dn_ancestors():
    _, javascript = _parts()
    script = (
        _between(javascript, "function prsAlarmEmpty", "function prsAlarmRememberDn")
        + _between(javascript, "function prsAlarmListField", "function prsAlarmOpenList")
        + r"""
function expect(actual, expected, label){
  if(actual!==expected) throw new Error(label+": "+JSON.stringify(actual));
}
expect(prsAlarmStateLabel({fired:1, finish:null, acked:null}), "Активна, не квитирована", "active nulls");
expect(prsAlarmStateLabel({fired:"2026-11-16T16:25:32", finish:"", acked:false}), "Активна, не квитирована", "active empties");
expect(prsAlarmStateLabel({fired:1, finish:0, acked:5}), "Активна, квитирована", "acked");
expect(prsAlarmStateLabel({fired:"t", finish:null, acked:"2026-11-16T16:26:00"}), "Активна, квитирована", "acked string");
expect(prsAlarmStateLabel({fired:100, finish:200, acked:null}), "Пропала, не квитирована", "gone keeps start");
expect(prsAlarmStateLabel({fired:false, finish:200, acked:""}), "Пропала, не квитирована", "gone empty fired");
expect(prsAlarmStateLabel({fired:1, finish:2, acked:3}), "", "gone acked is not drawn");
expect(prsAlarmStateLabel({fired:0, finish:null, acked:false}), "", "empty fired");
expect(prsAlarmEmpty(null)&&prsAlarmEmpty("")&&prsAlarmEmpty(0)&&prsAlarmEmpty(false), true, "empties");
expect(prsAlarmEmpty("0"), false, "string zero is a stamp");
var root="cn=objects,cn=prs";
var alarm="cn=Высокий,cn=Уровень,cn=Насос,cn=objects,cn=prs";
expect(prsAlarmDnUnder(alarm, root), true, "collapsed objects root");
expect(prsAlarmDnUnder(alarm, "cn=Насос,cn=objects,cn=prs"), true, "object");
expect(prsAlarmDnUnder(alarm, alarm), true, "the alarm itself");
expect(prsAlarmDnUnder(alarm, "cn=tags,cn=prs"), false, "other root");
expect(prsAlarmDnUnder("cn=objectsX,cn=prs", root), false, "suffix boundary");
expect(prsAlarmRootDn("objects"), root, "root dn");
expect(prsAlarmRootDn("tags"), "cn=tags,cn=prs", "tags root");
expect(prsAlarmIsGuid("objects"), false, "root is not a guid");
expect(prsAlarmIsGuid("8732294c-7312-1041-8c21-0dcaaf570565"), true, "guid");
var fields={};
function prsAlarmListHost(){return {querySelector:function(sel){return fields[sel.slice(1)]||null}}}
function prsAlarmUrl(query){return "https://stand/v1/alarms/"+(query||"")}
function prsTagGetTimeQueryValue(value){var text=String(value||"").trim();return text||null}
fields={
  "prs-alarm-key-parent":{value:"8732294c-7312-1041-8c21-0dcaaf570565"},
  "prs-alarm-key-getChildren":{checked:false},
  "prs-alarm-key-format":{checked:false},
  "prs-alarm-key-fired":{checked:true},
  "prs-alarm-key-start":{value:""},
  "prs-alarm-key-finish":{value:""},
  "prs-alarm-key-count":{value:""}
};
expect(prsAlarmListUrl(), "https://stand/v1/alarms/?parentId=8732294c-7312-1041-8c21-0dcaaf570565", "default is parent only");
fields["prs-alarm-key-fired"].checked=false;
fields["prs-alarm-key-getChildren"].checked=true;
fields["prs-alarm-key-count"].value="2";
expect(prsAlarmListUrl(), "https://stand/v1/alarms/?parentId=8732294c-7312-1041-8c21-0dcaaf570565&getChildren=true&fired=false&count=2", "changed keys");
expect(prsAlarmPathLabel("cn=Высокий уровень,cn=Уровень,cn=Насос,cn=Цех,cn=objects,cn=prs"), "Цех→Насос→Уровень", "object to tag");
expect(prsAlarmPathLabel("cn=Порог,cn=Давление,cn=tags,cn=prs"), "Давление", "tag only");
expect(prsAlarmPathLabel(""), "", "no dn");
"""
    )
    node = shutil.which("node")
    assert node, "Node.js is required to check alarm state classification"
    completed = subprocess.run([node, "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr or completed.stdout
