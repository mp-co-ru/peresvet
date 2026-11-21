import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "src/grafana/configurator/Configurator.json"


def _parts():
    options = json.loads(DASHBOARD.read_text(encoding="utf-8"))["panels"][0]["options"]
    return options["html"], options["css"], options["onRender"]


def test_alert_and_schedule_fields_are_not_squeezed_into_col_1():
    html, css, javascript = _parts()
    alert = html[html.index('id="div-alertConfig"'):html.index('id="div-scheduleConfig"')]
    schedule = html[html.index('id="div-scheduleConfig"'):html.index('id="div-catalogInstance"')]
    assert "prs-config-fields" in alert
    assert "col-1" not in alert
    assert "input-alertConfHigh" in alert
    assert "input-alertConfValue" in alert
    assert "input-alertConfAutoack" in alert
    assert "prs-config-fields" in schedule
    assert "col-2" not in schedule
    assert "input-scheduleConfStart" in schedule
    assert "input-scheduleConfEnd" in schedule
    assert ".prs-config-field{display:flex" in css
    assert "min-width:12rem" in css
    header = html[html.index('id="attributes-form"'):html.index('id="div-cn"')]
    assert 'class="prs-node-kind"' in header
    assert 'id="div-nodeType"' in header
    assert "white-space:nowrap" in css
    assert "function prsTreeDropDeleted" in javascript
    assert "prsTreeDropDeleted(s)" in javascript
    assert "methodById:(t&&t.byId)||{}" in javascript
    save = javascript.split("saveChanges=()", 1)[1].split("prsReorderMethodParameterIndices", 1)[0]
    ok_at = save.find('showAlert("div-updateAlert","div-updateAlertMessage","i-updateAlert","Свойства сохранены.",!0)')
    assert save.find("if(!r.ok)throw r") < ok_at < save.find("Ошибка обновления узла")
