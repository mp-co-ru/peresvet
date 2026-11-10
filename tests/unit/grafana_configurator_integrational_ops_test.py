"""Конфигуратор: первая GET- и первая SET-операция получают prsDefault."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"


def test_configurator_marks_first_operation_of_each_kind_as_default():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    javascript = dashboard["panels"][0]["options"]["onRender"]

    assert "function prsRebalanceLinkedOpDefaults()" in javascript
    assert 'a("Умолч."' in javascript
    assert "prsRebalanceLinkedOpDefaults(),C(),H()" in javascript
    assert "prsDefault=r.prsDefault===!0" in javascript
