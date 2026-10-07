import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
DOCS_HOST = "mp-co-ru.github.io/peresvet"
CODE_VERSION = "20261005-image-v1"


def _dashboard_parts():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    options = dashboard["panels"][0]["options"]
    return dashboard, options["html"], options["css"], options["onRender"]


def _read_pane(html: str) -> str:
    start = html.index('id="prs-tag-pane-read"')
    end = html.index('id="prs-tag-pane-write"')
    return html[start:end]


def test_tag_read_request_ux_dashboard_contract():
    dashboard, html, css, javascript = _dashboard_parts()
    read = _read_pane(html)

    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript

    # Copy-to-clipboard control next to formed GET URL
    assert 'id="span-tagGetDataURL"' in read
    assert 'id="button-tagCopyGetDataURL"' in read
    assert 'class="prs-copy-icon"' in read
    assert "fa-copy" not in read
    assert "fa-book-open" not in read
    assert 'class="prs-icon-btn flex-shrink-0" id="button-tagGetKeysToggle"' in read
    assert 'class="prs-tag-get-chevron"' in read
    assert "prsCopyTagGetDataURL" in javascript
    assert "prsCopyTextToClipboard" in javascript
    assert "navigator.clipboard" in javascript
    assert "execCommand(\"copy\")" in javascript or "execCommand('copy')" in javascript
    assert read.index("button-tagGetKeysToggle") < read.index("span-tagGetDataURL")
    assert read.index("span-tagGetDataURL") < read.index("button-tagCopyGetDataURL")
    assert 'class="prs-tag-get-url-prefix">GET ' in read

    # Collapsed summary + expand toggle (default collapsed)
    assert 'id="prs-tag-get-keys"' in read
    assert 'data-prs-expanded="0"' in read
    assert 'id="button-tagGetKeysToggle"' in read
    assert 'id="prs-tag-get-keys-summary"' in read
    assert 'id="prs-tag-get-keys-panel"' in read
    assert 'class="prs-tag-get-keys-panel d-none mt-2"' in read
    assert "prsToggleTagGetKeys" in javascript
    assert "prsRefreshTagGetKeysSummary" in javascript
    assert "prsRefreshTagGetKeysSummary(et)" in javascript

    # Each query key on its own row with tooltip + docs link
    key_order = (
        "format",
        "actual",
        "start",
        "finish",
        "count",
        "value",
        "timeStep",
        "maxCount",
    )
    last = -1
    for key in key_order:
        token = f'class="prs-tag-get-key-name">{key}</span>'
        assert token in read
        pos = read.index(token)
        assert pos > last
        last = pos

    assert read.count("fa-circle-info") == 9
    assert read.count('data-bs-toggle="tooltip"') == 8
    assert read.count("prs-tag-get-key-row-bool") == 2
    assert read.count("prs-docs-icon") == 8
    assert "input-group-text prs-tag-get-key-label" in read
    assert "#prs-tag-pane-read .prs-tag-get-keys-summary{display:none}" in css
    assert "prs-tag-get-key-label{gap:.35rem;background-color:#e9ecef}" in css
    assert "prs-tag-get-key-row-bool{display:flex;align-items:center;gap:.45rem}" in css
    assert "prs-tag-get-key-docs{display:inline-flex" in css
    assert "border-radius:50%" not in css.split("prs-tag-get-key-docs{")[1].split("}")[0]
    assert 'fill="#fff"' in read
    assert "#button-tagGetKeysToggle{margin-right:.85rem}" in css
    assert "#button-tagGetKeysToggle[aria-expanded=\"true\"] .prs-tag-get-chevron{transform:rotate(90deg)}" in css
    assert "i.fa-solid.fa-circle-info{box-sizing:border-box" in css
    assert "border-radius:50%" in css
    assert DOCS_HOST in read
    assert f"https://{DOCS_HOST}/historical_data.html#" in read
    assert "vovaman.github.io" not in read
    # Published Sphinx page: format lives in «Формат запроса…» (#id6);
    # other keys have stable heading ids.
    assert f"https://{DOCS_HOST}/historical_data.html#id6" in read
    assert "historical_data.html#getcurrentvalue" not in read
    for anchor in ("actual", "maxcount", "count", "timestep", "start", "finish", "value"):
        assert f"historical_data.html#{anchor}" in read

    # Keep both maxCount and count; do not rename to limit
    assert 'id="input-tagGetDataMaxCount"' in read
    assert 'id="input-tagGetDataCount"' in read
    assert 'id="input-tagGetDataLimit"' not in read
    assert ">limit<" not in read

    # start/finish are text fields: paste from the Time column and between fields
    assert 'id="input-tagGetDataStart"' in read
    assert 'id="input-tagGetDataFinish"' in read
    start_idx = read.index('id="input-tagGetDataStart"')
    finish_idx = read.index('id="input-tagGetDataFinish"')
    assert 'type="text"' in read[start_idx - 80 : start_idx]
    assert 'type="text"' in read[finish_idx - 80 : finish_idx]
    assert 'placeholder="микросекунды или дата/время"' in read
    assert 'id="button-tagGetDataStartClear"' in read
    assert 'id="button-tagGetDataFinishClear"' in read
    assert 'title="Сбросить"' in read
    assert "prsClearTagGetTime('input-tagGetDataStart')" in read
    assert "prsClearTagGetTime('input-tagGetDataFinish')" in read
    assert 'id="input-tagGetDataStartPicker"' in read
    assert 'id="input-tagGetDataFinishPicker"' in read
    assert "prsTagGetTimeQueryValue" in javascript
    assert "prsParseLooseDateTime" in javascript
    assert 'o&&(et.start=o)' in javascript
    assert 's&&(et.finish=s)' in javascript
    assert "prsStartDt.toISOString()" not in javascript
    assert "#prs-tag-pane-read .prs-tag-get-time{display:flex" in css

    # format checkbox still drives format=true
    assert (
        'id="input-tagGetDataFormat" onclick="formTagDataPanels();" '
        'checked="checked"'
    ) in read
    assert 'c.append("format","true")' in javascript

    # Scoped CSS must not redefine global method-param one-row flags
    assert "#prs-tag-pane-read .prs-tag-get-keys-summary" in css
    assert "#prs-tag-pane-read .prs-tag-get-key-row" in css

    # Write tab / export / results table preserved
    assert 'id="prs-tag-pane-write"' in html
    assert 'id="button-tagGetData"' in read
    assert 'id="button-tagExportCsv"' in read
    assert 'id="prs-tag-data-table"' in read
    assert 'id="tbody-tagData"' in read
    assert '<th scope="col" style="white-space:nowrap">Качество <i class="fa-solid fa-circle-info gray" title="' in read
    for code_line in (
        "0 или пусто — обычное значение, данные хорошие",
        "100 — разорвана связь между платформой и коннектором, значение null",
        "101 — связь между коннектором и платформой восстановлена после 100, значение null",
        "102 — разорвана связь между коннектором и поставщиком данных, значение null",
        "103 — ошибка источника данных",
        "104 — зарезервировано, больше не применяется",
    ):
        assert code_line in read
    assert "formTagDataPanels()" in read


def test_tag_read_request_preserves_method_param_flag_layout():
    _, html, _, _ = _dashboard_parts()
    # Method DG / head flags still use the shared one-row layout
    assert "prs-method-param-dg-flags" in html
    assert "prs-flags-one-row prs-method-param-dg-flags" in html
    assert "prs-flags-one-row prs-method-param-head-flags" in html
    # Read pane must not keep the old packed one-row flags
    read = _read_pane(html)
    assert "prs-flags-one-row" not in read
