import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261030-font-apply-v1"


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
    assert header.index('id="div-nodeName"') < header.index('id="button-copyNodeDn"')
    assert header.index('id="div-nodeId"') < header.index('id="button-copyNodeId"')
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
    assert '<div class="col d-flex align-items-center gap-2 prs-copy-pair"><span id="div-nodeId">' in header
    assert "prs-copy-pair" in header
    css = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    assert "#attributes-form .prs-copy-pair{display:flex;align-items:center;flex-wrap:wrap;column-gap:.75rem;row-gap:.25rem}" in css
    assert "#attributes-form .prs-copy-pair .prs-icon-btn{margin-left:.35rem}" in css
    assert "prs-copy-pair" in html[html.index('id="div-nodeName"') - 80 : html.index('id="div-nodeName"')]

    assert html.count('id="button-copyNodeDn"') == 1
    assert html.count('id="button-copyNodeId"') == 1
    assert "button-copy" not in cn
    assert "prs-copy-icon" not in cn
    assert "prsCopy" not in cn

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
