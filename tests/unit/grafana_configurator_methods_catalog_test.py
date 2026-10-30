import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261030-font-apply-v1"


def _parts():
    options = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]
    return options["html"], options["onRender"]


def test_methods_catalog_root_and_menus():
    html, javascript = _parts()
    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert '{id:"methods",text:"Методы",icon:"fa-solid fa-file-code",objectClass:"prsMethodsRoot"' in javascript
    assert '["objects","tags","connectors","schedules","dataStorages","methods","services"].forEach' in javascript
    assert '["catalogMethods","fa-file-code","Новый метод"]' in javascript
    assert "Новый метод каталога" not in javascript
    assert '["methodFolders","fa-folder","Новая папка"]' in javascript
    assert '"fa-folder":' in javascript
    assert 'prsIconOrder=["fa-circle-exclamation"' in javascript
    assert '"fa-folder"' in javascript.split("prsIconOrder=", 1)[1].split("];", 1)[0]
    assert "catalogMethodInstance" not in javascript
    assert "Метод из каталога" not in javascript
    assert "select-prsMethodKind" in html
    assert "prsOnMethodKindChange" in javascript
    assert "prsCreateInstanceMethod" in javascript
    assert "Вновь создаваемый метод" in html
    assert "Собственный метод" not in html
    assert "Ссылка на метод из каталога" in html
    assert 'if("methods"===t)return prsToolbarSelectRow(r),void prsCreateInstanceMethod(r);' in javascript
    assert 'if(("prsTag"===r||"prsAlert"===r)&&"tags"!==n&&"alerts"!==n)' in javascript
    assert 'itemDiv.setAttribute("data-parent-class",e.getAttribute("objectClass")||"")' in javascript
    parent_fn = javascript.split("function prsMethodTreeParentClass(){", 1)[1].split(
        "function prsTouchChanged", 1
    )[0]
    assert 'getAttribute("data-parent-class")' in parent_fn
    assert "previousElementSibling" in parent_fn
    assert 'prsMethod:{visible:["div-prsMethodAddress","div-prsMethodKind","div-prsCatalogMethodPick"' in javascript
    assert "Выберите метод каталога." in javascript
    assert 'case"prsMethodsRoot":a(["methodFolders","catalogMethods","methodDescription"])' in javascript
    assert 'case"prsModelNode":a(["methodFolders","catalogMethods","methodDescription","__active__","__delete__"])' in javascript
    assert '["methodDescription","fa-file-import","Загрузка описания"]' in javascript
    assert 'id="prs-method-description-dialog"' in html
    assert 'type="checkbox" id="prs-method-description-probe"' in html
    assert "Проверить методы" in html
    assert 'aria-label="Загрузить"' in html
    assert "prs-method-description-help" in html
    css = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    assert "#prs-method-description-dialog{white-space:normal}" in css
    assert 'id="prs-method-description-load"' in html
    assert 'prs-method-description-probe").addEventListener' not in javascript
    assert "/v1/methods/description" in javascript
    expand_at = javascript.find('if("prsMethodsRoot"===r||"prsModelNode"===r)')
    gate_at = javascript.find('let p=prsClassApi(r,t);if(!p)return;')
    assert expand_at != -1 and gate_at != -1 and expand_at < gate_at
    assert 'case"prsTag":a("tags"===n?["userFolders","tags"]:["__copy__","__active__","__delete__","alerts","methods"]);' in javascript
    assert 'case"prsAlert":a(["__copy__","methods","__active__","__delete__"]);' in javascript
    assert "prsSyncMethodCatalogForm" in javascript
    assert "prs.catalog.new" in javascript
    assert "/v1/methods/folders" not in javascript
    assert "prsCreateMethodFolder(row){prsCreateUserFolder(row)}" in javascript
    assert 'if("prsModelNode"===fallback&&"prsMethod"===oc)return' in javascript
    assert 'id="prs-catalog-method-dialog"' not in html
    assert 'id="input-prsCatalogMethodId"' in html
    assert 'id="div-prsMethodKind"' in html
    assert 'id="div-catalogInstance"' in html
    storage_at = html.index('id="prs-storage-tag-only"')
    assert "div-catalogInstance" not in html[storage_at : storage_at + 500]
    assert html.index('id="div-catalogInstance"') < html.index('id="div-parameters"')
    assert "function prsLoadCatalogMethod" in javascript
    assert "function prsSetMethodAddressLocked" in javascript
    assert "addr.readOnly=!0" in javascript
    bind_html = javascript.split("function prsBindFieldsHtml", 1)[1].split("function prsReadBindRow", 1)[0]
    assert "prs-method-param-head" in bind_html
    assert "prs-method-param-dg" in bind_html
    assert "prs-catalog-bind-rows" not in javascript.split("function prsRenderCatalogBindings", 1)[1].split("function prsMethodTreeParentClass", 1)[0]
    css = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    assert ".prs-method-mode-instance #div-parameters .prs-method-param-dg-host{display:none" not in css
    assert "addParameter(null,param,seq)" in javascript
    assert "Данные из запроса клиента" in javascript
    assert 'option value="platformRequest">Запрос к платформе' in javascript
    assert 'option value="httpRequest">Внешний запрос' in javascript
    assert 'id="div-param-platformRequest-only-${o}"' in javascript
    assert 'id="input-param-http-url-${o}"' in javascript
    assert 'id="div-param-tagData-query-${o}"' in javascript
    assert 'type="hidden" prsAttribute="parameter" id="input-parameter-prsIndex-${o}"' in javascript
    assert 'prs-flag-label">Индекс' not in javascript
    assert "function prsMethodParamSourceOf" in javascript
    assert ".prs-method-mode-instance #div-parameters{display:none" not in css
    assert ".prs-method-mode-instance .prs-method-param-add-wrap" in css
    assert "prs-catalog-vtype" in html
    assert "Целый" in html
