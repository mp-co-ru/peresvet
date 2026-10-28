import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261024-connector-config-tip-v1"


def _parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return options["html"], options["css"], options["onRender"]


def test_connector_config_form_contract():
    html, css, javascript = _parts()
    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert 'id="prs-config-slot"' in html
    assert 'id="div-prsConnectorConfigFields"' in html
    assert 'id="prs-connector-config-note"' in html
    assert 'id="prs-connector-config-list"' in html
    assert 'id="input-prsJsonConfigString"' in html
    assert "/*prsConnectorConfigStart*/" in javascript
    assert "/*prsConnectorConfigEnd*/" in javascript
    assert "prsConnectorLoadConfigForm=function" in javascript
    assert "prsConnectorConfigFieldValue=function" in javascript
    assert "prsConnectorConfigAppendSample=function" in javascript
    assert "prsConnectorRenderConfigFields=function" in javascript
    assert "prsConnectorResetConfigForm=function" in javascript
    assert 'window.location.origin+"/v1/connectors_app/config_example?id="' in javascript
    assert "prsConnectorLoadConfigForm()" in javascript
    assert "prsConnectorResetConfigForm()" in javascript
    assert ".prs-connector-config-label{" in css
    assert "prsConnectorConfigInfoIcon=function" in javascript
    assert 'data-bs-toggle","tooltip"' in javascript
    assert ".prs-connector-config-tip{" in css
    assert ".prs-connector-config-sample-json{" in css
    assert ".prs-config-slot{" in css


def test_connector_config_form_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_connector_config_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
