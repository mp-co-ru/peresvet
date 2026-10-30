import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261030-font-apply-v1"


def _on_render() -> str:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    return dashboard["panels"][0]["options"]["onRender"]


def test_api_urls_keep_the_page_origin():
    javascript = _on_render()

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "window.location.hostname" not in javascript
    assert 'window.location.protocol+"//"+window.location.hostname' not in javascript
    assert "${window.location.protocol}//${window.location.hostname}" not in javascript
    assert 'addNodeToHierarchy=e=>{url=window.location.origin+"/v1/"+e+"/"' in javascript
    assert 'Откройте https://"+window.location.host+"/grafana/' in javascript
    assert javascript.count("window.location.origin") == 57
