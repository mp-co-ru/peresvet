import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"


def _dashboard_parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return dashboard, options["html"], options["onRender"]


def test_csv_export_dashboard_contract():
    dashboard, html, javascript = _dashboard_parts()

    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert 'id="button-tagExportCsv"' in html
    assert 'class="prs-tag-export-wrap" title="Сохранить в CSV"' in html
    assert 'title="Сохранить в CSV"' in html
    assert "#button-tagExportCsv:disabled{pointer-events:none}" in (
        json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    )
    assert 'aria-label="Сохранить в CSV"' in html
    assert 'onclick="prsExportTagDataCsv();"' in html
    assert html.index('id="button-tagGetData"') < html.index(
        'id="button-tagExportCsv"'
    )
    assert "button-tagExportXlsx" not in html
    assert "Excel" not in html
    assert "xlsx" not in javascript.lower()
    assert "sheetjs" not in javascript.lower()

    for required_fragment in (
        'prsConfiguratorCodeVersion="20261009-services-splitter-v6"',
        "prsTagDataExportSnapshot",
        "prsBuildTagDataCsv",
        "prsExportTagDataCsv",
        "prsInvalidateTagDataExport",
        "prsSensitiveRequestKeys",
        "access_token",
        "url_userinfo",
        'n.push("x,y,q")',
        "requestLine",
        "text/csv",
        'prsTagDataCsvFileName(t)',
        'prsSafeExportFilePart(e&&e.tagName)+" :: "+prsFormatLocalDateTime(new Date())+".csv"',
    ):
        assert required_fragment in javascript

    assert 'id="input-tagSetDataTime"' in html
    assert "prsParseTagSetTimestamp" in javascript
    assert "prsTagSetPoint" in javascript
    assert "prsCoerceTagSetValue" in javascript
    assert 'Number(n("#input-prsValueTypeCode").attr("init-value"))' in javascript
    assert '<option value="6">Видеопоток</option>' in html
    assert 'id="input-prsCameraRtsp"' not in html
    assert 'id="div-videoTagPreview"' in html
    assert "prsShowVideoTagPreview" in javascript
    assert 'id="prs-video-preview-stage"' in html
    assert "Без start и finish — живой поток" in html
    assert "prsSyncVideoTagDataChrome" in javascript
    assert "prsSetVideoPlayButton" in javascript
    assert "prsTagDataPlayClick" in javascript
    assert "prsStopVideoMedia();prsSetVideoPlayButton(!1)" in javascript
    assert 'fa-solid fa-play' in javascript
    assert 'fa-solid fa-pause' in javascript
    assert '"6"===String(i.value)' in javascript
    assert "prsVideoPreviewCtl" in javascript
    assert "n.error&&(n.error.message||n.error.detail)" in javascript
    assert 'id="button-tagStopVideo"' not in html
    assert 'id="prs-video-ptz"' in html
    assert "prsBindVideoPtz" in javascript
    assert 'data-ptz="home"' in html
    assert 'data-ptz="pulse"' in html
    assert "prs-video-preview-row" in html
    assert html.index('id="prs-video-ptz"') < html.index('id="prs-video-preview-stage"')
    assert 'id="prs-video-image"' in html
    assert "prsRenderVideoImage" in javascript
    assert 'action:"image"' in javascript
    assert "fa-stop" not in html
    assert "Остановить поток" in javascript
    assert "prsStopVideoPreview" in javascript
    assert "window.prsTagDataPlayClick=prsTagDataPlayClick" in javascript
    assert "Тег видеопотока не привязывается к хранилищу истории" in javascript
    autolink = javascript[
        javascript.index('function(e,t){if("tags"===e&&6===Number') :
        javascript.index('}(e,node)', javascript.index('function(e,t){if("tags"===e&&6===Number'))
    ]
    assert "const n=" not in autolink
    assert "let n=" not in autolink
    assert "var n=" not in autolink
    assert "prsStorageUrl" in autolink
    assert "prsCameraOnRtspChange" not in javascript
    assert 'id="input-prsCameraArchivePath"' not in html
    assert 'id="input-prsCameraRetention"' not in html
    assert "prs-settings-video" not in html
    assert 'placeholder="микросекунды или дата/время"' in html
    assert 'id="input-tagSetDataTimePicker"' in html
    assert 'type="datetime-local"' in html[html.index('id="input-tagSetDataTime"') :]
    assert 'class="prs-tag-set-time-cal" title="Выбрать дату и время"' in html
    assert "prsFormatLocalDateTime" in javascript
    assert "prsApplyTagSetTimePicker" in javascript
    assert ".prs-tag-set-time-picker{position:absolute;inset:0;" in (
        json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    )

    dockerfile = (
        ROOT / "docker/docker-files/grafana/Dockerfile.grafana"
    ).read_text(encoding="utf-8")
    assert "sheetjs" not in dockerfile
    for script_name in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
    ):
        script = (ROOT / script_name).read_text(encoding="utf-8")
        assert "sheetjs" not in script


def test_method_save_omits_empty_parameter_description():
    _, _, javascript = _dashboard_parts()

    assert (
        "description:n(`#input-parameter-description-${index}`).val()||\"\""
        not in javascript
    )
    assert "d&&(a.description=d)" in javascript
    assert (
        "d=n(`#input-parameter-description-${index}`).val()" in javascript
    )


def test_csv_builder_writes_strings_or_microseconds():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for executable Grafana CSV validation")
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

    subprocess.run(
        [
            node,
            str(ROOT / "tests/unit/grafana_configurator_csv_node_test.js"),
            str(DASHBOARD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
