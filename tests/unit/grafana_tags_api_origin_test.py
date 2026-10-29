import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/tags/Теги.json"


def _panel() -> dict:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    return dashboard["panels"][0]


def test_tags_api_root_keeps_the_page_port():
    panel = _panel()
    javascript = panel["options"]["onRender"]

    assert "window.location.hostname" not in javascript
    assert "${window.location.protocol}//${window.location.hostname}" not in javascript
    assert "return `${window.location.origin}/v1`" in javascript
    assert panel["datasource"] == {"type": "datasource", "uid": "grafana"}
    assert panel["targets"] == []
    assert "marcusolsson-json-datasource" not in json.dumps(panel)
