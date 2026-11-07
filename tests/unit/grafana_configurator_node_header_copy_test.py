import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261102-catalog-params-read-v1"


def _parts():
    options = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]
    return options["html"], options["onRender"]


def _attributes_header(html: str) -> str:
    start = html.index('id="attributes-form"')
    end = html.index('id="div-cn"')
    return html[start:end]


def _cn_field(html: str) -> str:
    start = html.index('id="div-cn"')
    end = html.index('id="div-description"', start)
    return html[start:end]


def test_node_header_copy_buttons():
    html, javascript = _parts()
    header = _attributes_header(html)
    cn = _cn_field(html)

    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert "20261016-method-kind-v1" not in javascript

    assert 'id="button-copyNodeDn"' in header
    assert 'id="button-copyNodeId"' in header
    assert header.index('id="button-copyNodeDn"') < header.index('id="div-nodeName"')
    assert header.index('id="button-copyNodeId"') < header.index('id="div-nodeId"')
    assert html.index('id="button-copyNodeDn"') < html.index('id="div-cn"')
    assert html.index('id="button-copyNodeId"') < html.index('id="div-cn"')

    assert 'title="Копировать DN"' in header
    assert 'aria-label="Копировать DN"' in header
    assert 'title="Копировать идентификатор"' in header
    assert 'aria-label="Копировать идентификатор"' in header
    assert 'onclick="prsCopyNodeDn();"' in header
    assert 'onclick="prsCopyNodeId();"' in header

    assert 'class="prs-icon-btn flex-shrink-0" id="button-copyNodeDn"' in header
    assert 'class="prs-icon-btn flex-shrink-0" id="button-copyNodeId"' in header
    assert header.count('class="prs-copy-icon"') == 2
    assert "fa-copy" not in header
    assert "justify-content-between" not in header
    assert '<span id="div-nodeId">' in header
    assert '<div class="col d-flex align-items-center gap-2 prs-copy-pair"><button type="button" class="prs-icon-btn flex-shrink-0" id="button-copyNodeId"' in header
    assert "prs-copy-pair" in header
    css = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    assert "#attributes-form .prs-copy-pair{display:flex;align-items:center;flex-wrap:wrap;column-gap:.75rem;row-gap:.25rem}" in css
    assert "#attributes-form .prs-copy-pair .prs-icon-btn{margin-left:.35rem}" in css
    assert "#attributes-form .prs-attr-tools{margin-left:auto;display:inline-flex;align-items:center;flex:0 0 auto;gap:.45em}" in css
    assert "#attributes-form .prs-attr-slot{width:1.15em;height:1.15em;display:inline-flex;align-items:center;justify-content:center;flex:0 0 1.15em}" in css
    assert "#attributes-form .prs-attr-copy:hover,#attributes-form .prs-attr-docs:hover,#attributes-form .prs-attr-slot .fa-circle-info:hover{color:#143f4a;background:#c5e6ee;border-color:#2c707f;box-shadow:0 0 0 2px #2c707f}" in css
    name_at = html.index('id="div-nodeName"')
    assert "prs-copy-pair" in html[name_at - 900 : name_at]
    assert html.rfind('id="button-copyNodeDn"', 0, name_at) > html.rfind("prs-copy-pair", 0, name_at)

    assert html.count('id="button-copyNodeDn"') == 1
    assert html.count('id="button-copyNodeId"') == 1
    assert 'prsCopyField(\'input-cn\')' in cn
    assert 'title="Копировать имя"' in cn
    assert 'class="prs-attr-tools"' in cn
    assert cn.count('class="prs-attr-slot"') == 3
    assert cn.index('class="prs-attr-copy"') < cn.index("fa-circle-info")
    desc = html[html.index('id="div-description"') : html.index('id="div-prsMethodAddress"')]
    assert 'prsCopyField(\'input-description\')' in desc
    assert 'title="Копировать описание"' in desc
    assert desc.count('class="prs-attr-slot"') == 3
    assert desc.index('class="prs-attr-copy"') < desc.index("fa-circle-info")
    assert "Описание узла для операторов" in desc
    units = html[html.index('id="div-prsMeasureUnits"') : html.index('id="input-prsMeasureUnits"')]
    assert "fa-circle-info" in units
    assert "Единицы значения тега" in units
    assert html.count("M0 6.75") == 0
    assert 'fill="#fff" stroke="currentColor"' in html
    cfg = html[html.index('id="div-prsJsonConfigString"') : html.index('id="prs-json-editor-node"')]
    assert 'prsCopyField(\'input-prsJsonConfigString\')' in cfg
    assert 'title="Копировать конфигурацию"' in cfg
    assert cfg.count('class="prs-attr-slot"') == 3
    assert cfg.index('class="prs-attr-copy"') < cfg.index("fa-circle-info")
    active = html[html.index('id="div-prsActive"') : html.index('id="input-prsActive"')]
    assert "prsCopyField" not in active
    assert active.count('class="prs-attr-slot"') == 3
    assert html.count("prsCopyField(") == 3
    assert "prsCopyField=function(id)" in javascript
    assert 'id="but-save" type="button" class="prs-icon-btn disabled"' in html
    assert 'id="but-reset" type="button" class="prs-icon-btn disabled"' in html
    assert 'aria-label="Записать"' in html
    assert 'aria-label="Сбросить"' in html
    assert ">Сохранить</button>" not in html
    assert ">Сбросить</button>" not in html
    assert "prs-form-action-primary" not in html

    assert "prsCopyTextToClipboard=function" in javascript
    id_fn = javascript.split("prsCopyNodeId=function(){", 1)[1].split(
        "prsCopyNodeDn=function(){", 1
    )[0]
    dn_fn = javascript.split("prsCopyNodeDn=function(){", 1)[1].split(
        "prsToggleTagGetKeys=function", 1
    )[0]
    assert "prsCopyTextToClipboard(" in id_fn
    assert 'GetEl("div-nodeId")' in id_fn
    assert "prsCopyTextToClipboard(" in dn_fn
    assert "prsCurrentNodeDn" in dn_fn
    assert "div-nodeName" not in dn_fn
    assert "input-cn" not in dn_fn
    assert "#div-nodeName" not in dn_fn
    assert "#input-cn" not in dn_fn

    assert 'prsCurrentNodeDn=nodeData.dn||""' in javascript
    assert 'prsClearRightPane=function(){prsCurrentNodeDn="";' in javascript
    assert 'fillForm=e=>{prsInvalidateTagDataExport();prsCurrentNodeDn="";' in javascript
    assert "window.prsCopyNodeId=prsCopyNodeId" in javascript
    assert "window.prsCopyNodeDn=prsCopyNodeDn" in javascript
