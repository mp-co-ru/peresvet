import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
VENDOR_PATH = ROOT / "config/grafana/vendor/jsonata-2.0.6.min.js"
LICENSE_PATH = ROOT / "config/grafana/vendor/jsonata-2.0.6.LICENSE"
DOCKERFILE_PATH = ROOT / "docker/docker-files/grafana/Dockerfile.grafana"
VENDOR_SHA256 = "3616231ac3b165ea2b3e0840c94bbc0bf86b4c73202b644576693fd74dfbd762"
LOCAL_URL = "/grafana/public/vendor/jsonata-2.0.6.min.js"


def _on_render() -> str:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    return dashboard["panels"][0]["options"]["onRender"]


def test_configurator_loads_jsonata_from_grafana_static():
    javascript = _on_render()

    assert "cdn.jsdelivr.net" not in javascript
    assert "unpkg.com" not in javascript
    assert "import(" not in javascript
    assert f's.src="{LOCAL_URL}"' in javascript
    assert VENDOR_PATH.is_file()
    assert hashlib.sha256(VENDOR_PATH.read_bytes()).hexdigest() == VENDOR_SHA256
    assert LICENSE_PATH.read_text(encoding="utf-8").startswith("MIT license")
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert (
        "COPY config/grafana/vendor/jsonata-2.0.6.min.js "
        "/usr/share/grafana/public/vendor/jsonata-2.0.6.min.js"
    ) in dockerfile


def test_local_jsonata_loader_evaluates_without_network():
    node = shutil.which("node")
    assert node, "Node.js is required to check the local JSONata loader"
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_jsonata_vendor_node_test.js"),
            str(DASHBOARD_PATH),
            str(VENDOR_PATH),
        ],
        check=True,
    )
