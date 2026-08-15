import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
ASSET_DIR = ROOT / "config/grafana/vendor/sheetjs-0.18.5"


def _dashboard_parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return dashboard, options["html"], options["onRender"]


def test_xlsx_export_dashboard_contract():
    dashboard, html, javascript = _dashboard_parts()

    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert dashboard["version"] == 43
    assert 'id="button-tagExportXlsx"' in html
    assert 'disabled="disabled"' in html
    assert html.index('id="button-tagGetData"') < html.index(
        'id="button-tagExportXlsx"'
    )

    for required_fragment in (
        'prsConfiguratorCodeVersion="20260815-xlsx-export-v1"',
        "prsTagDataExportSnapshot",
        "prsInvalidateTagDataExport",
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


def test_sheetjs_asset_is_licensed_and_packaged():
    library = ASSET_DIR / "xlsx.full.min.js"
    license_file = ASSET_DIR / "LICENSE"

    assert library.stat().st_size > 100_000
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
