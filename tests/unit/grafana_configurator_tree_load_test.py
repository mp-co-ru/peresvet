import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261031-tree-load-once-v1"


def _javascript() -> str:
    options = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]
    return options["onRender"]


def test_slow_connector_load_does_not_append_a_second_copy():
    javascript = _javascript()

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "prsNextTreeLoad=function(row)" in javascript
    assert "prsTreeLoadAlive=function(row,gen)" in javascript
    assert 'row.setAttribute("data-prs-load-gen",String(gen))' in javascript
    assert "var prsLoadGen=prsNextTreeLoad(t);" in javascript
    assert "if(!prsTreeLoadAlive(t,prsLoadGen))return;if(e&&e.data){" in javascript
    assert 'prsLoadedNow&&(prsLoadedNow.innerHTML="")' in javascript
    assert 'prsSame.id===String(t.id))return prsSame' in javascript
    assert 'if(typeof prsTreeLoadAlive=="function"&&!prsTreeLoadAlive(e,prsLoadGen))return;var t=pair[0]' in javascript
    assert "var prsLoadGen=e.getAttribute(\"data-prs-load-gen\"),t=e.getAttribute(\"data-bs-target\")" in javascript
    assert "var prsStorageRow=e,prsLoadGen=prsNextTreeLoad(e);" in javascript
    assert "if(!prsTreeLoadAlive(prsStorageRow,prsLoadGen))return;a.innerHTML=\"\";" in javascript
    assert 'prsSame.id===String(t.id))return}var r=prsLdapAttrFirst' in javascript


def test_tree_load_generation_discards_a_stale_response():
    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("Node.js is not installed")
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_tree_load_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
