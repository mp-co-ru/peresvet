import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
ASSET_DIR = ROOT / "config/grafana/vendor/sheetjs-0.18.5"
SHEETJS_SHA256 = "c9506197caf809a075b6dee1da0d36fb19da7158ffe8a88e7b0c96c5d8623c99"


def _dashboard_parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return dashboard, options["html"], options["onRender"]


def test_xlsx_export_dashboard_contract():
    dashboard, html, javascript = _dashboard_parts()

    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert dashboard["version"] == 45
    assert 'id="button-tagExportXlsx"' in html
    assert 'disabled="disabled"' in html
    assert html.index('id="button-tagGetData"') < html.index(
        'id="button-tagExportXlsx"'
    )

    for required_fragment in (
        'prsConfiguratorCodeVersion="20260815-xlsx-export-v3"',
        "prsTagDataExportSnapshot",
        "prsInvalidateTagDataExport",
        "prsValidateExportSnapshot",
        "prsReadResponseText",
        "prsSensitiveRequestKeys",
        'i.t="s"',
        "delete i.f",
        "content-length",
        "body.getReader",
        "access_token",
        "url_userinfo",
        "rawResponseText",
        "dataPoints",
        '"Metadata"',
        '"Data"',
        '"Raw response"',
        "URL.revokeObjectURL",
        "sheetjs-0.18.5/xlsx.full.min.js",
    ):
        assert required_fragment in javascript

    assert "cdn.sheetjs.com" not in javascript
    assert "unpkg.com" not in javascript
    assert "prsSafeExcelCell" not in javascript


def test_sheetjs_asset_is_licensed_and_packaged():
    library = ASSET_DIR / "xlsx.full.min.js"
    license_file = ASSET_DIR / "LICENSE"

    assert library.stat().st_size > 100_000
    assert hashlib.sha256(library.read_bytes()).hexdigest() == SHEETJS_SHA256
    assert "Apache License" in license_file.read_text(encoding="utf-8")

    dockerfile = (
        ROOT / "docker/docker-files/grafana/Dockerfile.grafana"
    ).read_text(encoding="utf-8")
    expected_source = "config/grafana/vendor/sheetjs-0.18.5/"
    expected_target = (
        "/usr/share/grafana/public/vendor/peresvet/sheetjs-0.18.5/"
    )
    assert expected_source in dockerfile
    assert expected_target in dockerfile

    for script_name in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
    ):
        script = (ROOT / script_name).read_text(encoding="utf-8")
        assert '"config/grafana/vendor/sheetjs-0.18.5"' in script


def test_embedded_helpers_and_xlsx_round_trip(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for executable Grafana XLSX validation")
    try:
        subprocess.run(
            [node, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Node.js executable is present but cannot run")

    _, _, javascript = _dashboard_parts()
    embedded_script = tmp_path / "configurator-on-render.js"
    embedded_script.write_text(javascript, encoding="utf-8")
    subprocess.run(
        [node, "--check", str(embedded_script)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_xlsx_node_test.js"),
            str(DASHBOARD_PATH),
            str(ASSET_DIR / "xlsx.full.min.js"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
