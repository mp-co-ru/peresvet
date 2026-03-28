#!/usr/bin/env python3
"""Patch Configurator.json: tag↔DB UX (Grafana HTML panel)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "src/configurator_grafana/Configurator.json"

# Insert before toolbar end marker in onRender
NEW_BLOCK = r"""
prsTagLinkageBound = false;
prsTagLinkageBusy = false;
prsTagLinkageDsMeta = {};

function prsTagDsEntityType(ds) {
  var a = ds && ds.attributes && ds.attributes.prsEntityTypeCode;
  var v = Array.isArray(a) ? a[0] : a;
  var n = parseInt(String(v), 10);
  return isFinite(n) ? n : null;
}

function prsHideTagIntegrationalPanel() {
  var panel = __prsConfiguratorHtmlNode.getElementById("prs-ds-linked-tag-panel");
  if (panel && panel.dataset.fromTagForm === "1") {
    panel.classList.add("d-none");
    panel.dataset.fromTagForm = "";
  }
  if (typeof prsSyncRightPlaceholder === "function") prsSyncRightPlaceholder();
}

function prsFetchAllDataStoragesWithTags(cb) {
  var url = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  var p = new URLSearchParams();
  p.append("base", "");
  p.append("getLinkedTags", "true");
  p.append("getLinkedAlerts", "false");
  ["cn", "prsDefault", "prsEntityTypeCode"].forEach(function (a) { p.append("attributes", a); });
  fetch(url + "?" + p.toString(), { headers: { "Content-type": "application/json" } })
    .then(function (r) { return r.json(); })
    .then(function (data) { cb(null, data && data.data ? data.data : []); })
    .catch(function (e) { cb(e, []); });
}

function prsFetchAllConnectorsWithTags(cb) {
  var url = window.location.protocol + "//" + window.location.hostname + "/v1/connectors/";
  var p = new URLSearchParams();
  p.append("base", "");
  p.append("getLinkedTags", "true");
  ["cn"].forEach(function (a) { p.append("attributes", a); });
  fetch(url + "?" + p.toString(), { headers: { "Content-type": "application/json" } })
    .then(function (r) { return r.json(); })
    .then(function (data) { cb(null, data && data.data ? data.data : []); })
    .catch(function (e) { cb(e, []); });
}

function prsFindTagDataStorageId(allDs, tagId) {
  for (var i = 0; i < allDs.length; i++) {
    var lt = allDs[i].linkedTags || [];
    for (var j = 0; j < lt.length; j++) {
      var tid = lt[j].tagId || (lt[j].attributes && prsLdapAttrFirst(lt[j].attributes.cn));
      if (String(tid) === String(tagId)) return allDs[i].id;
    }
  }
  return "";
}

function prsFindTagConnectorId(allConn, tagId) {
  for (var i = 0; i < allConn.length; i++) {
    var lt = allConn[i].linkedTags || [];
    for (var j = 0; j < lt.length; j++) {
      var tid = lt[j].tagId || (lt[j].attributes && prsLdapAttrFirst(lt[j].attributes.cn));
      if (String(tid) === String(tagId)) return allConn[i].id;
    }
  }
  return "";
}

function prsRefreshTagTreeHints() {
  prsFetchAllDataStoragesWithTags(function (_err, allDs) {
    var map = {};
    allDs.forEach(function (ds) {
      var cn = prsLdapAttrFirst(ds.attributes && ds.attributes.cn) || ds.id;
      (ds.linkedTags || []).forEach(function (lnk) {
        var tid = lnk.tagId || (lnk.attributes && prsLdapAttrFirst(lnk.attributes.cn));
        if (tid) map[String(tid)] = { id: ds.id, cn: cn };
      });
    });
    __prsConfiguratorHtmlNode.querySelectorAll('#tree .list-group-item[objectClass="prsTag"]').forEach(function (row) {
      if (row.id === "tags") return;
      row.classList.remove("prs-tag-tree-linked", "prs-tag-tree-unlinked");
      var info = map[row.id];
      if (info) {
        row.classList.add("prs-tag-tree-linked");
        row.setAttribute("title", "Хранилище данных: " + info.cn);
      } else {
        row.classList.add("prs-tag-tree-unlinked");
        row.setAttribute("title", "Нет привязки к хранилищу данных");
      }
    });
  });
}

function prsBindTagLinkageSelectorsOnce() {
  if (prsTagLinkageBound) return;
  prsTagLinkageBound = true;
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var selCn = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedConnector");
  if (selDs) {
    selDs.addEventListener("change", function () {
      if (prsTagLinkageBusy) return;
      prsApplyTagStorageSelection();
    });
  }
  if (selCn) {
    selCn.addEventListener("change", function () {
      if (prsTagLinkageBusy) return;
      prsApplyTagConnectorSelection();
    });
  }
}

function prsFillSelectStorageOptions(sel, allDs, currentId) {
  if (!sel) return;
  sel.innerHTML = '<option value="">— не привязан —</option>';
  allDs.forEach(function (ds) {
    var cn = prsLdapAttrFirst(ds.attributes && ds.attributes.cn) || ds.id;
    var opt = document.createElement("option");
    opt.value = ds.id;
    opt.textContent = cn + "  (" + ds.id + ")";
    sel.appendChild(opt);
  });
  sel.value = currentId || "";
  if (currentId && sel.value !== currentId) sel.value = "";
}

function prsFillSelectConnectorOptions(sel, allConn, currentId) {
  if (!sel) return;
  sel.innerHTML = '<option value="">— не привязан —</option>';
  allConn.forEach(function (c) {
    var cn = prsLdapAttrFirst(c.attributes && c.attributes.cn) || c.id;
    var opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = cn + "  (" + c.id + ")";
    sel.appendChild(opt);
  });
  sel.value = currentId || "";
  if (currentId && sel.value !== currentId) sel.value = "";
}

function prsFillTagLinkageUI(tagId) {
  prsBindTagLinkageSelectorsOnce();
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var selCn = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedConnector");
  prsHideTagIntegrationalPanel();
  prsFetchAllDataStoragesWithTags(function (e1, allDs) {
    if (e1) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Не удалось загрузить хранилища.", false);
    }
    prsTagLinkageDsMeta = {};
    allDs.forEach(function (ds) {
      var cn = prsLdapAttrFirst(ds.attributes && ds.attributes.cn) || ds.id;
      prsTagLinkageDsMeta[ds.id] = { cn: cn, entityType: prsTagDsEntityType(ds) };
    });
    var curDs = prsFindTagDataStorageId(allDs, tagId);
    prsFillSelectStorageOptions(selDs, allDs, curDs);
    prsFetchAllConnectorsWithTags(function (e2, allConn) {
      if (e2) {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Не удалось загрузить коннекторы.", false);
      }
      var curC = prsFindTagConnectorId(allConn, tagId);
      prsFillSelectConnectorOptions(selCn, allConn, curC);
      prsTagLinkageBusy = true;
      if (selDs) selDs.dataset.prsInitial = selDs.value;
      if (selCn) selCn.dataset.prsInitial = selCn.value;
      prsTagLinkageBusy = false;
      prsMaybeShowIntegrationalOpsForTagForm(tagId);
    });
  });
}

function prsMaybeShowIntegrationalOpsForTagForm(tagId) {
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  if (!selDs || !selDs.value) {
    prsHideTagIntegrationalPanel();
    return;
  }
  var meta = prsTagLinkageDsMeta[selDs.value];
  var et = meta && meta.entityType;
  if (et === 2) {
    var fake = document.createElement("div");
    fake.setAttribute("data-ds-id", selDs.value);
    fake.setAttribute("data-entity-id", tagId);
    fake.setAttribute("objectClass", "prsDsLinkedTag");
    var panel = __prsConfiguratorHtmlNode.getElementById("prs-ds-linked-tag-panel");
    if (panel) {
      panel.classList.remove("d-none");
      panel.dataset.fromTagForm = "1";
    }
    prsPopulateDsLinkedTagPanel(fake);
    if (typeof prsSyncRightPlaceholder === "function") prsSyncRightPlaceholder();
  } else {
    prsHideTagIntegrationalPanel();
  }
}

function prsApplyTagStorageSelection() {
  var tagId = ($("#div-nodeId").text() || "").trim();
  var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  if (!sel || !tagId) return;
  var prev = (sel.dataset.prsInitial || "").trim();
  var next = (sel.value || "").trim();
  if (prev === next) {
    prsMaybeShowIntegrationalOpsForTagForm(tagId);
    return;
  }
  prsTagLinkageBusy = true;
  var urlBase = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  function put(body) {
    return fetch(urlBase, {
      method: "PUT",
      body: JSON.stringify(body),
      headers: new Headers({ "Content-Type": "application/json" })
    });
  }
  function done(ok) {
    prsTagLinkageBusy = false;
    if (ok) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "Привязка к хранилищу обновлена.", true);
      sel.dataset.prsInitial = next;
      prsRefreshTagTreeHints();
      prsRefreshDataStorages();
    } else {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу (ожидался 202).", false);
      prsFillTagLinkageUI(tagId);
    }
    prsMaybeShowIntegrationalOpsForTagForm(tagId);
  }
  if (prev) {
    put({ id: prev, unlinkTags: [tagId] }).then(function (r1) {
      if (r1.status !== 202) { done(false); return; }
      if (!next) { done(true); return; }
      put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r2) {
        done(r2.status === 202);
      }).catch(function () { done(false); });
    }).catch(function () { done(false); });
  } else if (next) {
    put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r) {
      done(r.status === 202);
    }).catch(function () { done(false); });
  } else {
    prsTagLinkageBusy = false;
  }
}

function prsApplyTagConnectorSelection() {
  var tagId = ($("#div-nodeId").text() || "").trim();
  var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedConnector");
  if (!sel || !tagId) return;
  var prev = (sel.dataset.prsInitial || "").trim();
  var next = (sel.value || "").trim();
  if (prev === next) return;
  prsTagLinkageBusy = true;
  var urlBase = window.location.protocol + "//" + window.location.hostname + "/v1/connectors/";
  function put(body) {
    return fetch(urlBase, {
      method: "PUT",
      body: JSON.stringify(body),
      headers: new Headers({ "Content-Type": "application/json" })
    });
  }
  function done(ok) {
    prsTagLinkageBusy = false;
    if (ok) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "Привязка к коннектору обновлена.", true);
      sel.dataset.prsInitial = next;
    } else {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к коннектору (ожидался 202).", false);
      prsFillTagLinkageUI(tagId);
    }
  }
  if (prev) {
    put({ id: prev, unlinkTags: [tagId] }).then(function (r1) {
      if (r1.status !== 202) { done(false); return; }
      if (!next) { done(true); return; }
      put({
        id: next,
        linkedTags: [{ tagId: tagId, attributes: { prsJsonConfigString: {} } }]
      }).then(function (r2) {
        done(r2.status === 202);
      }).catch(function () { done(false); });
    }).catch(function () { done(false); });
  } else if (next) {
    put({
      id: next,
      linkedTags: [{ tagId: tagId, attributes: { prsJsonConfigString: {} } }]
    }).then(function (r) {
      done(r.status === 202);
    }).catch(function () { done(false); });
  } else {
    prsTagLinkageBusy = false;
  }
}
""".strip(
    "\n"
)


def main() -> None:
    data = json.loads(CFG.read_text(encoding="utf-8"))
    opts = data["panels"][0]["options"]
    html: str = opts["html"]
    js: str = opts["onRender"]
    css: str = opts.get("css", "")

    marker = "/*__PRS_TOOLBAR_BLOCK_END__*/"
    if marker not in js:
        raise SystemExit(f"marker {marker!r} not found in onRender")
    if "prsFillTagLinkageUI" in js:
        raise SystemExit("patch already applied?")

    js = js.replace(marker, NEW_BLOCK + "\n\n" + marker, 1)

    # --- HTML: checkbox ---
    ins = (
        '\t\t\t<div class="px-2 py-2 prs-auto-link-wrap prs-border-subtle">\n'
        '\t\t\t\t<div class="form-check smaller mb-0">\n'
        '\t\t\t\t\t<input class="form-check-input" type="checkbox" id="chk-autoLinkTagDefault" checked>\n'
        '\t\t\t\t\t<label class="form-check-label" for="chk-autoLinkTagDefault">'
        "Привязывать тег к базе по умолчанию при создании</label>\n"
        "\t\t\t\t</div>\n"
        "\t\t\t</div>\n"
    )
    anchor = (
        '\t\t\t</div>\n'
        '\t\t\t<div id="div-butAlert" class="alert alert-message alert-dismissible d-flex rounded p-0 mt-3 d-none"'
    )
    if anchor not in html:
        raise SystemExit("checkbox anchor not found")
    html = html.replace(anchor, "</div>\n" + ins + anchor, 1)

    drop_block = (
        '\t\t\t<div class="input-group mt-2 d-none" id="div-prsDataStorageDrop">\n'
        '\t\t\t\t<span class="input-group-text prs-input-label space-between">Привязка из дерева</span>\n'
        '\t\t\t\t<div class="form-control prs-drop-zone p-2" style="min-height:3.5rem;height:auto;" '
        'id="prs-storage-detail-drop" data-drop-storage="">Перетащите сюда тег или тревогу</div>\n'
        "\t\t\t</div>\n"
    )
    if drop_block not in html:
        raise SystemExit("drop block not found")
    html = html.replace(drop_block, "", 1)

    tag_links = (
        '\t\t\t<div class="input-group mt-2" id="div-prsTagDataStorageLink">\n'
        '\t\t\t\t<span class="input-group-text prs-input-label space-between">Хранилище данных\n'
        '\t\t\t\t\t\t<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip" '
        'title="Одна привязка на тег. Смена хранилища отвязывает от предыдущего."></i>\n'
        "\t\t\t\t\t</span>\n"
        '\t\t\t\t<select class="form-select" id="select-prsTagLinkedStorage">\n'
        '\t\t\t\t\t<option value="">— не привязан —</option>\n'
        "\t\t\t\t</select>\n"
        "\t\t\t</div>\n"
        '\t\t\t<div class="input-group mt-2" id="div-prsTagConnectorLink">\n'
        '\t\t\t\t<span class="input-group-text prs-input-label space-between">Коннектор\n'
        '\t\t\t\t\t\t<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip" '
        'title="Одна привязка на тег. Смена коннектора отвязывает от предыдущего."></i>\n'
        "\t\t\t\t\t</span>\n"
        '\t\t\t\t<select class="form-select" id="select-prsTagLinkedConnector">\n'
        '\t\t\t\t\t<option value="">— не привязан —</option>\n'
        "\t\t\t\t</select>\n"
        "\t\t\t</div>\n"
    )
    desc_anchor = (
        '\t\t\t</div>\n'
        '\t\t\t<div class="input-group mt-2" id="div-prsMethodAddress">'
    )
    if desc_anchor not in html:
        raise SystemExit("method address anchor not found")
    html = html.replace(desc_anchor, "</div>\n" + tag_links + "\n" + desc_anchor, 1)

    opts["html"] = html

    css_add = """

/* Автопривязка тегов */
.prs-border-subtle { border-bottom: 1px solid var(--prs-border, #dee2e6); }

/* Дерево: цветом — привязан к БД / нет */
#tree .list-group-item.prsTag.prs-tag-tree-linked {
  border-left: 3px solid var(--ioterra-teal, #2c707f);
  padding-left: calc(0.5rem - 3px);
}
#tree .list-group-item.prsTag.prs-tag-tree-unlinked {
  border-left: 3px solid var(--ioterra-rust, #a34a28);
  opacity: 0.92;
}
"""
    if ".prs-tag-tree-linked" not in css:
        opts["css"] = css.rstrip() + css_add

    js = js.replace(
        '"visible": ["div-cn", "div-description", "div-prsDataStorageDrop", "div-prsActive", "div-prsDefault", "div-prsEntityTypeCode", "div-prsJsonConfigString"],',
        '"visible": ["div-cn", "div-description", "div-prsActive", "div-prsDefault", "div-prsEntityTypeCode", "div-prsJsonConfigString"],',
    )
    js = js.replace(
        '"div-scheduleConfig", "div-prsDataStorageDrop"]',
        '"div-scheduleConfig"]',
    )
    js = js.replace(
        '"div-prsEntityTypeCode", "div-prsDataStorageDrop"]',
        '"div-prsEntityTypeCode"]',
    )
    js = js.replace(
        '"div-scheduleConfig", "div-tagData", "div-prsDataStorageDrop"]',
        '"div-scheduleConfig", "div-tagData"]',
    )
    js = js.replace(
        '"visible": ["div-prsValueTypeCode", "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-tagData"],\n'
        '    "hidden": ["div-prsIndex", "div-prsMethodAddress", "div-prsDefault", "div-prsJsonConfigString",\n'
        '      "div-initiatedBy", "div-parameters", "div-alertConfig", "div-scheduleConfig", "div-prsEntityTypeCode", "div-prsDataStorageDrop"]',
        '"visible": ["div-prsValueTypeCode", "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-tagData",\n'
        '      "div-prsTagDataStorageLink", "div-prsTagConnectorLink"],\n'
        '    "hidden": ["div-prsIndex", "div-prsMethodAddress", "div-prsDefault", "div-prsJsonConfigString",\n'
        '      "div-initiatedBy", "div-parameters", "div-alertConfig", "div-scheduleConfig", "div-prsEntityTypeCode"]',
    )

    js = js.replace(
        '  if (node.objectClass === "prsTag" || node.objectClass === "prsAlert") {\n'
        '    itemDiv.setAttribute("draggable", "true");\n'
        '    itemDiv.setAttribute("title", "Перетащите на хранилище для привязки");\n'
        "  }\n",
        "  /* drag-and-drop привязка отключена */\n",
    )

    js = js.replace(
        "prsPopulateStorageSidePanel = function (el) {\n"
        "  var id = el.id;\n"
        '  var dz = __prsConfiguratorHtmlNode.getElementById("prs-storage-detail-drop");\n'
        "  if (dz) {\n"
        '    dz.setAttribute("data-drop-storage", id);\n'
        "    prsBindDataStorageDropZones();\n"
        "  }\n"
        "  if (typeof prsSyncRightPlaceholder === \"function\") prsSyncRightPlaceholder();\n"
        "};",
        "prsPopulateStorageSidePanel = function (_el) {\n"
        "  if (typeof prsSyncRightPlaceholder === \"function\") prsSyncRightPlaceholder();\n"
        "};",
    )

    js = js.replace(
        '$("#tree").on("dragstart", "div.list-group-item.prsTag, div.list-group-item.prsAlert", function (e) {\n'
        "  const ev = e.originalEvent;\n"
        "  if (ev && ev.dataTransfer) {\n"
        '    ev.dataTransfer.setData("text/plain", this.id);\n'
        '    ev.dataTransfer.setData("application/x-prs-class", this.getAttribute("objectClass") || "");\n'
        '    ev.dataTransfer.effectAllowed = "copyMove";\n'
        "  }\n"
        "});\n",
        "",
    )

    js = js.replace(
        "queueMicrotask(function () {\n"
        "  try {\n"
        "    prsLoadAutoLinkPref();\n"
        "    prsRefreshDataStorages();\n"
        "  } catch (_prsde) {}\n"
        "});\n",
        "queueMicrotask(function () {\n"
        "  try {\n"
        "    prsLoadAutoLinkPref();\n"
        "    prsRefreshDataStorages();\n"
        "    if (typeof prsRefreshTagTreeHints === \"function\") prsRefreshTagTreeHints();\n"
        "  } catch (_prsde) {}\n"
        "});\n",
    )

    js = js.replace(
        '    showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert",\n'
        '      "Создан узел без автопривязки. Перетащите тег/тревогу на карточку хранилища слева.", true);\n',
        '    showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert",\n'
        '      "Создан узел без автопривязки. Выберите хранилище в свойствах тега.", true);\n',
    )

    old_bind = """function prsBindDataStorageDropZones() {
  __prsConfiguratorHtmlNode.querySelectorAll("[data-drop-storage]").forEach((zone) => {
    const sid = zone.getAttribute("data-drop-storage");
    zone.addEventListener("dragover", function (e) { e.preventDefault(); zone.classList.add("prs-drag-over"); });
    zone.addEventListener("dragleave", function () { zone.classList.remove("prs-drag-over"); });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      zone.classList.remove("prs-drag-over");
      const tagId = e.dataTransfer.getData("text/plain");
      const oc = e.dataTransfer.getData("application/x-prs-class");
      if (!tagId) return;
      prsLinkEntityToStorage(sid, tagId, oc);
    });
  });
}

function prsLinkEntityToStorage(storageId, entityId, objectClass) {
  const urlDs = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  const payload = { id: storageId };
  if (objectClass === "prsAlert") payload.linkedAlerts = [{ alertId: entityId }];
  else payload.linkedTags = [{ tagId: entityId }];
  fetch(urlDs, {
    method: "PUT",
    body: JSON.stringify(payload),
    headers: new Headers({ "Content-Type": "application/json" })
  }).then((response) => {
    if (response.status !== 202) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу", false);
      return;
    }
    showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "Привязка к хранилищу выполнена.", true);
    prsRefreshDataStorages();
    var _dsRowL = __prsConfiguratorHtmlNode.getElementById(storageId);
    if (_dsRowL && _dsRowL.getAttribute("aria-expanded") && typeof prsLoadLinkedEntitiesUnderStorage === "function") {
      prsLoadLinkedEntitiesUnderStorage(_dsRowL);
    }
  });
}
"""
    if old_bind not in js:
        raise SystemExit("drop-zone block not found")
    js = js.replace(old_bind, "function prsBindDataStorageDropZones() {}\n", 1)

    js = js.replace("    prsBindDataStorageDropZones();\n", "")

    js = js.replace(
        '    if (objClass === "prsDataStorage") {\n'
        '      var dzSt = __prsConfiguratorHtmlNode.getElementById("prs-storage-detail-drop");\n'
        "      if (dzSt) {\n"
        '        dzSt.setAttribute("data-drop-storage", nodeId);\n'
        "        prsBindDataStorageDropZones();\n"
        "      }\n"
        "    }\n\n",
        "",
    )

    js = js.replace(
        '    // для тега подготовим панели работы с данными\n'
        '    if (objClass === "prsTag")\n'
        '      changeTagDataPanelOnSave();\n'
        "    formTagDataPanels();\n",
        '    // для тега подготовим панели работы с данными\n'
        '    if (objClass === "prsTag") {\n'
        "      changeTagDataPanelOnSave();\n"
        "      prsFillTagLinkageUI(nodeId);\n"
        "    } else {\n"
        "      prsHideTagIntegrationalPanel();\n"
        "    }\n"
        "    formTagDataPanels();\n",
    )

    js = js.replace(
        "    }).then((response) => {\n"
        "      if (response.status !== 202) {\n"
        '        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу по умолчанию.", false);\n'
        "        return;\n"
        "      }\n"
        "    });\n",
        "    }).then((response) => {\n"
        "      if (response.status !== 202) {\n"
        '        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу по умолчанию.", false);\n'
        "        return;\n"
        "      }\n"
        '      if (typeof prsRefreshTagTreeHints === "function") prsRefreshTagTreeHints();\n'
        "    });\n",
    )

    opts["onRender"] = js

    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK:", CFG)


if __name__ == "__main__":
    main()
