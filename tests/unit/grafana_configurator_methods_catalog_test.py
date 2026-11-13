import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261113-method-type-tip-v1"


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
    assert ">Метод/ссылка<" in html
    assert ">Тип метода<" not in html
    assert 'id="select-prsMethodEntityType"' in html
    assert ">Вычислительный<" in html
    assert ">Чтение<" in html
    assert ">Запись<" in html
    assert ">Действие при чтении<" in html
    assert ">Действие при записи<" in html
    assert "3 — действие при чтении: метод получает чтение и ответ не отправляет" in html
    assert "4 — действие при записи: метод получает запись и ответ не отправляет" in html
    assert "prsSyncMethodEntityTypeControl" in javascript
    assert "prs-method-variadic-instance" in javascript
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
    assert 'prsMethod:{visible:["div-prsMethodAddress","div-prsVariadic","div-initiatedBy","div-parameters","div-prsEntityTypeCode"]' in javascript
    assert 'catalogNode=prsMethodIsCatalogNode(node)' in javascript
    assert 'variadicBox.classList.toggle("d-none",!catalogNode)' in javascript
    assert "prsApplyVariadicParametersVisibility" in javascript
    assert 'if(nodeData&&nodeData.id&&String(node.id)!==String(nodeData.id))return;' in javascript
    assert 'if(!he(prsMethodRenderId))return;try{prsSyncMethodCatalogForm(nodeData)}' in javascript
    assert "prsFormSeq!==window.prsFormLoadSeq||!he(t)" in javascript
    assert "prs-method-variadic" in javascript
    assert "if(he(t)){setAttributesVisibility(e);nodeData=a.data[0];" in javascript
    assert "Да — параметры задаются там, где метод применяется. Нет — параметры заданы здесь." in html
    assert "Выберите метод каталога." in javascript
    assert 'case"prsMethodsRoot":a(["methodFolders","catalogMethods","methodDescription"])' in javascript
    assert 'case"prsModelNode":a(["methodFolders","catalogMethods","methodDescription","__active__","__delete__"])' in javascript
    assert '["methodDescription","fa-file-import","Загрузка описания"]' in javascript
    assert 'id="prs-method-description-dialog"' in html
    assert 'type="checkbox" id="prs-method-description-probe"' in html
    assert "Проверить методы" in html
    assert 'aria-label="Загрузить"' in html
    assert "prs-method-description-help" in html
    assert 'accept=".yaml,.yml,.json,application/yaml,text/yaml,application/json"' in html
    assert 'class="prs-method-description-pick"' in html
    assert 'for="prs-method-description-file"' in html
    assert 'id="prs-method-description-name"' in html
    assert "prsShowMethodDescriptionName" in javascript
    assert 'name.endsWith(".json")' in javascript
    assert "Выберите файл YAML или JSON." in javascript
    css = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]["css"]
    assert "#prs-method-description-dialog{white-space:normal}" in css
    assert 'id="prs-method-description-load"' in html
    assert 'prs-method-description-probe").addEventListener' not in javascript
    assert "/v1/methods/description" not in javascript
    assert "prsParseMethodDescription=function" in javascript
    assert "prsImportMethodDescription=function" in javascript
    assert 'return prsPostJson(window.location.origin+"/v1/methods/",body)' in javascript
    assert "folder:!0" in javascript
    assert 'data={error:{message:"Ответ сервера "+resp.status}}' in javascript
    expand_at = javascript.find('if("prsMethodsRoot"===r||"prsModelNode"===r)')
    gate_at = javascript.find('let p=prsClassApi(r,t);if(!p)return;')
    assert expand_at != -1 and gate_at != -1 and expand_at < gate_at
    assert 'return qsF.append("filter",JSON.stringify({objectClass:["prsFolder"]})),fetch(' in javascript[expand_at:gate_at]
    assert 'else if("methods"===prsFolderCtx)prsFolderJobs.push(prsFolderFetch("/v1/methods/","prsMethod"))' in javascript
    assert '"prsMethod"!==oc)return' in javascript
    assert 'case"prsMethod":node.icon="fa-solid fa-file-code prsMethod"' in javascript
    assert 'case"prsTag":a("tags"===n?["userFolders","tags"]:["__copy__","__active__","__delete__","alerts","methods"]);' in javascript
    assert 'case"prsAlert":a(["__copy__","methods","__active__","__delete__"]);' in javascript
    assert "prsSyncMethodCatalogForm" in javascript
    assert "prs.catalog.new" in javascript
    assert "/v1/methods/folders" not in javascript
    assert "prsCreateMethodFolder(row){prsCreateUserFolder(row)}" in javascript
    assert 'if("prsModelNode"===fallback&&"prsMethod"===oc)return' in javascript
    assert 'id="prs-catalog-method-dialog"' not in html
    assert 'id="input-prsCatalogMethodId"' in html
    assert 'id="div-prsVariadic"' in html
    assert "prs-tag-method-conflict" in javascript
    assert "Тег привязан к хранилищу и к методу чтения или записи" in javascript
    assert 'n.classList.toggle("d-none",1===a||2===a)' in javascript
    assert "prsVariadic" in javascript
    assert 'if(!a.length)return""' in javascript
    assert "Укажите тег, из которого берутся данные. Ключ value только фильтрует данные этого тега." in javascript
    assert "Тег не выбран. Без него запрос GET /v1/data не читает данные." in javascript
    assert 'id="div-prsMethodKind"' in html
    assert 'id="div-catalogInstance"' in html
    storage_at = html.index('id="prs-storage-tag-only"')
    assert "div-catalogInstance" not in html[storage_at : storage_at + 500]
    assert html.index('id="div-catalogInstance"') < html.index('id="div-parameters"')
    assert "function prsMethodIsCatalogNode" in javascript
    assert 'prsMethodIsCatalogNode(node)||"prsModelNode"===poc' in javascript
    assert 'if("catalog"!==prsMode)a.prsJsonConfigString=e' in javascript
    assert '"input-parameter-description-"' in javascript
    assert "function prsLoadCatalogMethod" in javascript
    assert '"/v1/methods/?id="+encodeURIComponent(id)+"&attributes=cn&attributes=description&attributes=prsMethodAddress&attributes=objectClass' in javascript
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
    assert "#attributes-form.prs-method-mode-instance.prs-method-variadic-instance .prs-method-param-add-wrap{display:block!important}" in css
    assert ".prs-method-mode-catalog .prs-method-param-head-flags,.prs-method-mode-instance .prs-method-param-head-flags{flex-direction:column!important" in css
    assert ".prs-method-mode-catalog .prs-method-param-head-flags>.prs-catalog-vtype" in css
    assert "prs-catalog-vtype" in html
    assert "Целый" in html


def test_method_description_yaml_is_parsed_in_the_configurator():
    import shutil
    import subprocess

    node = shutil.which("node")
    assert node
    _html, javascript = _parts()
    start = javascript.find("prsParseMethodDescription=function")
    assert start > 0
    depth = 0
    end = start
    for index, char in enumerate(javascript[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    script = javascript[start:end] + r"""
const text = `
folders:
  - cn: Видео
    methods:
      - cn: person_in_zone
        address: prs.vision.person_in_zone
        description: |
          Первая строка
          Вторая строка
        parameters:
          - cn: zone
            index: 2
            prsValueTypeCode: 4
`;
const tree = prsParseMethodDescription(text);
if (tree.folders[0].cn !== "Видео") throw new Error("folder");
const method = tree.folders[0].methods[0];
if (method.address !== "prs.vision.person_in_zone") throw new Error("address");
if (method.parameters[0].prsValueTypeCode !== 4) throw new Error("type");
if (!String(method.description).includes("Вторая строка")) throw new Error("description");
console.log("ok");
"""
    completed = subprocess.run([node, "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_catalog_method_follows_methods_tree_not_only_direct_parent():
    import shutil
    import subprocess

    node = shutil.which("node")
    assert node
    _html, javascript = _parts()
    start = javascript.find("function prsMethodIsCatalogNode")
    end = javascript.find("function prsTouchChanged", start)
    assert start > 0 and end > start
    script = javascript[start:end] + r"""
function el(id, objectClass, parent) {
  return {
    id: id,
    parentElement: parent || null,
    getAttribute(name) {
      if (name === "objectClass") return objectClass || "";
      if (name === "role") return "treeitem";
      return "";
    },
  };
}
const methods = el("methods", "prsMethodsRoot", null);
const methodsGroup = { previousElementSibling: methods, getAttribute() { return ""; } };
const folder = el("stdlib", "prsFolder", methodsGroup);
const folderGroup = { previousElementSibling: folder, getAttribute() { return ""; } };
const nested = el("add-in-folder", "prsMethod", folderGroup);
const rootMethod = el("add", "prsMethod", methodsGroup);
const tag = el("tag-1", "prsTag", null);
const tagGroup = { previousElementSibling: tag, getAttribute() { return ""; } };
const onTag = el("local", "prsMethod", tagGroup);
const tagFolder = el("folder-on-tag", "prsFolder", tagGroup);
const tagFolderGroup = { previousElementSibling: tagFolder, getAttribute() { return ""; } };
const underTagFolder = el("m", "prsMethod", tagFolderGroup);
if (!prsMethodIsCatalogNode(rootMethod)) throw new Error("root method");
if (!prsMethodIsCatalogNode(nested)) throw new Error("folder method");
if (prsMethodIsCatalogNode(onTag)) throw new Error("tag method");
if (prsMethodIsCatalogNode(underTagFolder)) throw new Error("folder under tag");
console.log("ok");
"""
    completed = subprocess.run([node, "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
