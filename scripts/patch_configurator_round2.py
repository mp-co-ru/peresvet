#!/usr/bin/env python3
"""Round-2 patches for Configurator linked-tag UI (see user request 2026-03)."""
import json
from pathlib import Path

ROOT = Path("/home/vovaman/work/projects/peresvet")
PATH = ROOT / "src/configurator_grafana/Configurator.json"

HELPERS = r"""
function prsDeepMergeSet(root, parts, value) {
  if (!parts || !parts.length) return;
  var k = parts[0];
  if (parts.length === 1) {
    root[k] = value;
    return;
  }
  if (!root[k] || typeof root[k] !== "object" || Array.isArray(root[k])) root[k] = {};
  prsDeepMergeSet(root[k], parts.slice(1), value);
}

function prsNormalizeJsonataPathForParams(expr) {
  if (expr == null) return [];
  var s = String(expr).trim();
  if (s.indexOf("$") === 0) s = s.replace(/^\$\./, "").replace(/^\$/, "");
  return s.split(".").filter(function (x) { return x.length > 0; });
}

function prsBuildIntegrationalParamsBlob(userVals) {
  var blob = {};
  if (!prsLinkedTagEntryState || !prsLinkedTagEntryState.operations || !userVals || typeof userVals !== "object") return blob;
  var getOp = null;
  prsLinkedTagEntryState.operations.forEach(function (op) {
    var etc = op.attributes && parseInt(String(op.attributes.prsEntityTypeCode != null ? op.attributes.prsEntityTypeCode : 0), 10);
    if (etc === 0) getOp = op;
  });
  if (!getOp || !Array.isArray(getOp.parameters)) return blob;
  getOp.parameters.forEach(function (p) {
    var cn = prsFirstStr(p.attributes && p.attributes.cn) || "";
    if (!cn || !(cn in userVals)) return;
    var cfg = prsParseJsonMaybe(p.attributes && p.attributes.prsJsonConfigString);
    var pathExpr = cfg.JSONata != null ? String(cfg.JSONata) : ("params." + cn);
    var parts = prsNormalizeJsonataPathForParams(pathExpr);
    if (!parts.length) return;
    var v = userVals[cn];
    if (parts[0] === "params") {
      prsDeepMergeSet(blob, parts.slice(1), v);
    } else {
      prsDeepMergeSet(blob, parts, v);
    }
  });
  return blob;
}

function prsMarkLinkedTagOpsDirty() {
  prsLinkedTagOpsDirtyFlag = true;
  if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
}

function prsFillLinkedOpParamRowsIntoSlot(oi) {
  var root = __prsConfiguratorHtmlNode;
  var slot = root.getElementById("prs-linked-op-params-slot-" + oi);
  if (!slot || !prsLinkedTagEntryState) return;
  prsSyncLinkedOpParametersFromSql(oi);
  slot.innerHTML = "";
  var op = prsLinkedTagEntryState.operations[oi];
  var params = Array.isArray(op.parameters) ? op.parameters : [];
  var lp = document.createElement("div");
  lp.className = "fw-semibold smaller mb-1 text-muted";
  lp.textContent = "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b SQL (\u0438\u0437 :placeholder)";
  slot.appendChild(lp);
  if (params.length === 0) {
    var np = document.createElement("div");
    np.className = "text-muted small";
    np.textContent = "\u041d\u0435\u0442 :\u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u043e\u0432 \u0432 SQL.";
    slot.appendChild(np);
    return;
  }
  for (var pi = 0; pi < params.length; pi++) {
    slot.appendChild(prsBuildLinkedParamRow(oi, pi));
  }
}

function prsRefreshLinkedOpParamRows(oi) {
  prsFillLinkedOpParamRowsIntoSlot(oi);
}

function prsSaveLinkedTagV2Promise() {
  return new Promise(function (resolve) {
    var root = __prsConfiguratorHtmlNode;
    var panel = root.getElementById("prs-ds-linked-tag-panel");
    var ta = root.getElementById("textarea-prs-ds-linked-tag-ops");
    if (!panel || !prsLinkedTagEntryState) {
      resolve(false);
      return;
    }
    if (panel.dataset.entityClass === "prsDsLinkedAlert") {
      resolve(false);
      return;
    }
    var dsId = panel.dataset.dsId;
    var entId = panel.dataset.entityId;
    if (!dsId || !entId) {
      resolve(false);
      return;
    }
    var parsed = prsLinkedTagPayloadFromState();
    var v2url = window.location.protocol + "//" + window.location.hostname + "/v2/dataStorages/?id=" + encodeURIComponent(dsId) + "&getLinkedTags=true";
    fetch(v2url, { headers: { "Content-type": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var one = data && data.data && data.data[0];
        var lt = one && one.linkedTags ? one.linkedTags.slice() : [];
        if (!parsed.tagId) parsed.tagId = entId;
        var idx = -1;
        for (var i = 0; i < lt.length; i++) {
          if (String(lt[i].tagId) === String(parsed.tagId)) { idx = i; break; }
        }
        if (idx >= 0) lt[idx] = parsed;
        else lt.push(parsed);
        return fetch(window.location.protocol + "//" + window.location.hostname + "/v2/dataStorages/", {
          method: "PUT",
          body: JSON.stringify({ id: dsId, linkedTags: lt }),
          headers: new Headers({ "Content-Type": "application/json" })
        });
      })
      .then(function (response) {
        var ok = response && response.status === 202;
        if (!ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0438 linkedTags (v2)", false);
        } else {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "linkedTags \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d.", true);
        }
        resolve(ok);
      })
      .catch(function () {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0438 v2", false);
        resolve(false);
      });
  });
}

"""

NEW_BUILD_PANE = r"""function prsBuildLinkedOpPaneContent(oi) {
  var wrap = document.createElement("div");
  wrap.className = "prs-linked-op-pane-inner w-100";
  var op = prsLinkedTagEntryState.operations[oi];
  var a = op.attributes || {};
  var cfg = (a.prsJsonConfigString && typeof a.prsJsonConfigString === "object") ? a.prsJsonConfigString : {};
  function mkMini(label, controlEl, flexGrow) {
    var ig = document.createElement("div");
    ig.className = "input-group input-group-sm prs-linked-op-mini flex-shrink-0";
    if (flexGrow) ig.style.flex = flexGrow;
    var sp = document.createElement("span");
    sp.className = "input-group-text prs-input-label prs-linked-op-lbl text-truncate";
    sp.style.maxWidth = "7.5rem";
    sp.textContent = label;
    sp.title = label;
    ig.appendChild(sp);
    if (controlEl.classList && (controlEl.classList.contains("form-control") || controlEl.classList.contains("form-select"))) {
      ig.appendChild(controlEl);
    } else {
      var w = document.createElement("div");
      w.className = "flex-grow-1 min-w-0 d-flex align-items-stretch";
      w.appendChild(controlEl);
      ig.appendChild(w);
    }
    return ig;
  }
  var metaRow = document.createElement("div");
  metaRow.className = "d-flex flex-wrap align-items-end gap-1 mt-1 prs-linked-op-meta-row";
  var del = document.createElement("button");
  del.type = "button";
  del.className = "btn btn-sm btn-outline-danger flex-shrink-0";
  del.style.marginBottom = "1px";
  del.innerHTML = '<i class="fa-solid fa-trash"></i>';
  del.title = "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044e";
  del.onclick = function () { prsLinkedOpRemove(oi); };
  metaRow.appendChild(del);
  var iCn = document.createElement("input");
  iCn.type = "text";
  iCn.className = "form-control form-control-sm";
  iCn.value = prsFirstStr(a.cn) || "";
  iCn.oninput = function () { prsLinkedOpPatch(oi, "cn", iCn.value); };
  iCn.onblur = function () { prsRenderLinkedTagOpsEditor(); };
  metaRow.appendChild(mkMini("\u0418\u043c\u044f (cn)", iCn, "2 1 120px"));
  var sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  var o0 = document.createElement("option"); o0.value = "0"; o0.textContent = "GET";
  var o1 = document.createElement("option"); o1.value = "1"; o1.textContent = "SET";
  sel.appendChild(o0); sel.appendChild(o1);
  sel.value = String((a.prsEntityTypeCode === 1 || a.prsEntityTypeCode === "1") ? 1 : 0);
  sel.onchange = function () {
    prsLinkedOpPatch(oi, "prsEntityTypeCode", sel.value === "1" ? 1 : 0);
    try { if (typeof prsTagIntegRefreshReadPanel === "function") prsTagIntegRefreshReadPanel(); } catch (_e2) {}
  };
  metaRow.appendChild(mkMini("\u0422\u0438\u043f", sel, "1 1 72px"));
  var fcAct = document.createElement("span");
  fcAct.className = "form-control form-control-sm d-flex align-items-center py-0";
  fcAct.style.minHeight = "calc(1.5em + 0.5rem + 2px)";
  var cb = document.createElement("input");
  cb.type = "checkbox";
  cb.className = "prs-tag-data-toggle-input";
  cb.checked = a.prsActive !== false && a.prsActive !== "FALSE";
  cb.onchange = function () { prsLinkedOpPatch(oi, "prsActive", cb.checked); };
  fcAct.appendChild(cb);
  metaRow.appendChild(mkMini("\u0410\u043a\u0442.", fcAct, "0 0 auto"));
  var iTm = document.createElement("input");
  iTm.type = "number";
  iTm.className = "form-control form-control-sm";
  iTm.step = "1";
  iTm.value = String(cfg.timeoutMs != null ? cfg.timeoutMs : 5000);
  iTm.oninput = function () { var n = parseFloat(iTm.value); prsLinkedOpPatchJson(oi, "timeoutMs", isFinite(n) ? n : 5000); };
  metaRow.appendChild(mkMini("t/o ms", iTm, "1 1 76px"));
  var iMr = document.createElement("input");
  iMr.type = "number";
  iMr.className = "form-control form-control-sm";
  iMr.step = "1";
  iMr.value = String(cfg.maxRows != null ? cfg.maxRows : 10000);
  iMr.oninput = function () { var n = parseFloat(iMr.value); prsLinkedOpPatchJson(oi, "maxRows", isFinite(n) ? n : 10000); };
  metaRow.appendChild(mkMini("maxR", iMr, "1 1 72px"));
  var iVer = document.createElement("input");
  iVer.type = "number";
  iVer.className = "form-control form-control-sm";
  iVer.step = "1";
  iVer.value = String(cfg.version != null ? cfg.version : 1);
  iVer.oninput = function () { var n = parseFloat(iVer.value); prsLinkedOpPatchJson(oi, "version", isFinite(n) ? n : 1); };
  metaRow.appendChild(mkMini("ver", iVer, "0 0 56px"));
  wrap.appendChild(metaRow);
  var taq = document.createElement("textarea");
  taq.className = "form-control form-control-sm prs-mono flex-grow-1";
  taq.rows = 5;
  taq.value = cfg.query || "";
  taq.oninput = function () { prsLinkedOpPatchJson(oi, "query", taq.value); };
  taq.onblur = function () {
    prsSyncLinkedOpParametersFromSql(oi);
    prsSyncLinkedTagTextarea();
    prsRefreshLinkedOpParamRows(oi);
  };
  var igSql = document.createElement("div");
  igSql.className = "input-group input-group-sm mt-2 align-items-stretch";
  var spSql = document.createElement("span");
  spSql.className = "input-group-text prs-input-label align-self-start";
  spSql.textContent = "SQL";
  igSql.appendChild(spSql);
  igSql.appendChild(taq);
  wrap.appendChild(igSql);
  var slot = document.createElement("div");
  slot.id = "prs-linked-op-params-slot-" + oi;
  slot.className = "prs-linked-sql-params-slot";
  wrap.appendChild(slot);
  prsFillLinkedOpParamRowsIntoSlot(oi);
  return wrap;
}
"""

CSS_APPEND = """

/* вкладки операций привязки тега — как верхние Свойства/Хранилище */
#prs-linked-op-tabs {
  display: flex;
  flex-wrap: nowrap;
  align-items: flex-end;
  gap: 0;
  margin: 0;
  padding: 0;
  border: none;
  border-bottom: 1px solid #d0d5d8;
  background: transparent;
  border-radius: 6px 6px 0 0;
}
#prs-linked-op-tabs .nav-item { margin: 0; list-style: none; }
#prs-linked-op-tabs .nav-link {
  position: relative;
  margin: 0 0 0 -1px;
  padding: 0.4rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #6c757d;
  background: #f2f2f2;
  border: 1px solid #d0d5d8 !important;
  border-bottom-color: #d0d5d8;
  border-radius: 0;
  cursor: pointer;
}
#prs-linked-op-tabs .nav-item:first-child .nav-link { margin-left: 0; }
#prs-linked-op-tabs .nav-link.active {
  margin-bottom: -1px;
  font-weight: 700;
  color: #212529 !important;
  background: #fff !important;
  border-bottom-color: #fff !important;
  z-index: 2;
}
#prs-linked-op-tabs .nav-link:hover:not(.active) {
  background: #e8e8e8;
  color: #495057;
}
.prs-linked-op-meta-row .prs-linked-op-mini { min-width: 0; }
.prs-linked-op-tab-content {
  border-top-left-radius: 0 !important;
}
"""

OLD_HTML_BLOCK = (
    '<div id="prs-ds-linked-tag-ops-editor" class="prs-linked-ops-editor mb-2"></div>\n'
    '\t\t\t\t<details class="prs-linked-raw-json mb-2 small" id="prs-ds-linked-tag-json-details">\n'
    '\t\t\t\t\t<summary class="text-muted user-select-none">Показать / править JSON</summary>\n'
    '\t\t\t\t\t<textarea id="textarea-prs-ds-linked-tag-ops" class="form-control form-control-sm prs-mono mt-1" rows="8" placeholder="{}"></textarea>\n'
    '\t\t\t\t\t<button type="button" class="btn btn-sm btn-outline-secondary mt-1 me-1" onclick="prsApplyLinkedTagJsonFromTextarea();">Применить JSON к форме</button>\n'
    '\t\t\t\t</details>\n'
    '\t\t\t\t<button type="button" class="btn btn-sm btn-outline-secondary me-1 mb-1" onclick="prsReloadDsLinkedTagOps();">Обновить из v2</button>\n'
    '\t\t\t\t<button type="button" class="btn btn-sm btn-primary mb-1" onclick="prsSaveDsLinkedTagOps();">Записать PUT v2</button>'
)

NEW_HTML_BLOCK = (
    '<div id="prs-ds-linked-tag-ops-editor" class="prs-linked-ops-editor mb-2"></div>\n'
    '\t\t\t\t<textarea id="textarea-prs-ds-linked-tag-ops" class="d-none" aria-hidden="true" tabindex="-1"></textarea>'
)

OLD_SAVE_BTN = (
    '<button id="but-save" type="button" class="btn btn-primary btn-icon btn-sm prs-icon-only disabled" onclick="saveChanges();" title="Записать" aria-label="Записать">'
)
NEW_SAVE_BTN = (
    '<button id="but-save" type="button" class="btn btn-primary btn-icon btn-sm prs-icon-only disabled" onclick="saveChanges();" '
    'title="Записать изменения узла (в т.ч. операции интеграционного хранилища)" aria-label="Записать" data-bs-toggle="tooltip" data-bs-placement="bottom">'
)

OLD_RESET_BTN = (
    '<button id="but-reset" type="button" class="btn btn-secondary btn-icon btn-sm prs-icon-only disabled" onclick="resetChanges();" title="Сбросить" aria-label="Сбросить">'
)
NEW_RESET_BTN = (
    '<button id="but-reset" type="button" class="btn btn-secondary btn-icon btn-sm prs-icon-only disabled" onclick="resetChanges();" '
    'title="Сбросить несохранённые изменения" aria-label="Сбросить" data-bs-toggle="tooltip" data-bs-placement="bottom">'
)


def main():
    cfg = json.loads(PATH.read_text(encoding="utf-8"))
    on = cfg["panels"][0]["options"]["onRender"]
    html = cfg["panels"][0]["options"]["html"]
    css = cfg["panels"][0]["options"]["css"]

    if OLD_HTML_BLOCK not in html:
        raise SystemExit("OLD_HTML_BLOCK not in html")
    html = html.replace(OLD_HTML_BLOCK, NEW_HTML_BLOCK, 1)

    if OLD_SAVE_BTN not in html:
        raise SystemExit("OLD_SAVE_BTN not in html")
    html = html.replace(OLD_SAVE_BTN, NEW_SAVE_BTN, 1)
    if OLD_RESET_BTN not in html:
        raise SystemExit("OLD_RESET_BTN not in html")
    html = html.replace(OLD_RESET_BTN, NEW_RESET_BTN, 1)

    if "#prs-linked-op-tabs" not in css:
        css = css + CSS_APPEND

    # --- onRender: insert dirty flag after prsLinkedTagActiveOpTab
    needle = "var prsLinkedTagActiveOpTab = 0;"
    if needle not in on:
        raise SystemExit("prsLinkedTagActiveOpTab line missing")
    ins = needle + "\nvar prsLinkedTagOpsDirtyFlag = false;"
    if "prsLinkedTagOpsDirtyFlag" not in on:
        on = on.replace(needle, ins, 1)

    # Insert helpers before prsTagIntegBuildDraftFromGetOp
    anchor = "function prsTagIntegBuildDraftFromGetOp() {"
    if anchor not in on:
        raise SystemExit(anchor + " not found")
    if "prsBuildIntegrationalParamsBlob" not in on:
        on = on.replace(anchor, HELPERS + "\n" + anchor, 1)

    # Replace prsBuildLinkedOpPaneContent function
    start = on.find("function prsBuildLinkedOpPaneContent(oi) {")
    end = on.find("function prsBuildLinkedParamRow(oi, pi) {", start)
    if start < 0 or end < 0:
        raise SystemExit("prsBuildLinkedOpPaneContent bounds")
    on = on[:start] + NEW_BUILD_PANE + "\n\n" + on[end:]

    # Toolbar buttons: + only
    on = on.replace(
        'add0.innerHTML = \'<i class="fa-solid fa-plus"></i> Операция\';',
        'add0.className = "btn btn-sm btn-primary prs-method-param-add-btn flex-shrink-0";\n    add0.innerHTML = \'<span><i class="fa-solid fa-plus"></i></span>\';\n    add0.title = "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044e";',
        1,
    )
    on = on.replace(
        'addB.className = "btn btn-sm btn-outline-primary flex-shrink-0";\n  addB.innerHTML = \'<i class="fa-solid fa-plus"></i> Операция\';',
        'addB.className = "btn btn-sm btn-primary prs-method-param-add-btn flex-shrink-0";\n  addB.innerHTML = \'<span><i class="fa-solid fa-plus"></i></span>\';\n  addB.title = "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044e";',
        1,
    )

    # Tab list: add border-bottom-0 removal — use prs-linked-op-tabs styles
    on = on.replace(
        'tabsUl.className = "nav nav-tabs nav-tabs-sm flex-grow-1 min-w-0 flex-nowrap overflow-auto mb-0 border-bottom-0";',
        'tabsUl.className = "nav nav-tabs nav-tabs-sm flex-grow-1 min-w-0 flex-nowrap overflow-auto mb-0";',
        1,
    )
    on = on.replace(
        'tabBtn.className = "nav-link py-1 px-2" + (oi === activeIdx ? " active" : "");',
        'tabBtn.className = "nav-link" + (oi === activeIdx ? " active" : "");',
        1,
    )

    # formTagDataPanels: integrational params blob
    OLD_INT = """        if (pobj && typeof pobj === "object" && !Array.isArray(pobj)) {
          pTagGet.append("params", JSON.stringify(pobj));
        }"""
    NEW_INT = """        if (pobj && typeof pobj === "object" && !Array.isArray(pobj)) {
          var paramsBlob = typeof prsBuildIntegrationalParamsBlob === "function" ? prsBuildIntegrationalParamsBlob(pobj) : pobj;
          if (paramsBlob && typeof paramsBlob === "object" && Object.keys(paramsBlob).length > 0) {
            pTagGet.append("params", JSON.stringify(paramsBlob));
          }
        }"""
    if OLD_INT not in on:
        raise SystemExit("OLD_INT block not found")
    on = on.replace(OLD_INT, NEW_INT, 1)

    # prsLinkedOpPatch + prsLinkedOpPatchJson + prsLinkedParamPatchJson — mark dirty
    on = on.replace(
        "  op.attributes[key] = val;\n  prsSyncLinkedTagTextarea();\n}",
        "  op.attributes[key] = val;\n  prsSyncLinkedTagTextarea();\n  prsMarkLinkedTagOpsDirty();\n}",
        1,
    )
    # second occurrence is prsLinkedParamPatch - skip by targeting prsLinkedOpPatch only
    # Re-read: first replace might hit wrong one. Be specific:
    patch_fn = """function prsLinkedOpPatch(oi, key, val) {
  var op = prsLinkedTagEntryState.operations[oi];
  if (!op) return;
  if (!op.attributes) op.attributes = {};
  op.attributes[key] = val;
  prsSyncLinkedTagTextarea();
}"""
    if patch_fn in on:
        on = on.replace(
            patch_fn,
            """function prsLinkedOpPatch(oi, key, val) {
  var op = prsLinkedTagEntryState.operations[oi];
  if (!op) return;
  if (!op.attributes) op.attributes = {};
  op.attributes[key] = val;
  prsSyncLinkedTagTextarea();
  prsMarkLinkedTagOpsDirty();
}""",
            1,
        )

    pj = """function prsLinkedOpPatchJson(oi, key, val) {
  var op = prsLinkedTagEntryState.operations[oi];
  if (!op) return;
  if (!op.attributes) op.attributes = {};
  if (!op.attributes.prsJsonConfigString || typeof op.attributes.prsJsonConfigString !== "object") {
    op.attributes.prsJsonConfigString = { query: "", timeoutMs: 5000, maxRows: 10000, version: 1 };
  }
  op.attributes.prsJsonConfigString[key] = val;
  prsSyncLinkedTagTextarea();
}"""
    if pj in on:
        on = on.replace(
            pj,
            pj.replace(
                "  prsSyncLinkedTagTextarea();\n}",
                "  prsSyncLinkedTagTextarea();\n  prsMarkLinkedTagOpsDirty();\n}",
            ),
            1,
        )

    ppj = """function prsLinkedParamPatchJson(oi, pi, key, val) {
  var op = prsLinkedTagEntryState.operations[oi];
  if (!op || !op.parameters[pi]) return;
  if (!op.parameters[pi].attributes) op.parameters[pi].attributes = {};
  if (!op.parameters[pi].attributes.prsJsonConfigString || typeof op.parameters[pi].attributes.prsJsonConfigString !== "object") {
    op.parameters[pi].attributes.prsJsonConfigString = {};
  }
  op.parameters[pi].attributes.prsJsonConfigString[key] = val;
  prsSyncLinkedTagTextarea();
}"""
    if ppj in on:
        on = on.replace(
            ppj,
            ppj.replace(
                "  prsSyncLinkedTagTextarea();\n}",
                "  prsSyncLinkedTagTextarea();\n  prsMarkLinkedTagOpsDirty();\n}",
            ),
            1,
        )

    # prsLinkedOpAdd / Remove — mark dirty (after render they already patch - add explicit)
    on = on.replace(
        "  prsLinkedTagActiveOpTab = prsLinkedTagEntryState.operations.length - 1;\n  prsRenderLinkedTagOpsEditor();\n}",
        "  prsLinkedTagActiveOpTab = prsLinkedTagEntryState.operations.length - 1;\n  prsMarkLinkedTagOpsDirty();\n  prsRenderLinkedTagOpsEditor();\n}",
        1,
    )
    on = on.replace(
        "  else if (oi === was) prsLinkedTagActiveOpTab = Math.min(was, prsLinkedTagEntryState.operations.length - 1);\n  prsRenderLinkedTagOpsEditor();\n}",
        "  else if (oi === was) prsLinkedTagActiveOpTab = Math.min(was, prsLinkedTagEntryState.operations.length - 1);\n  prsMarkLinkedTagOpsDirty();\n  prsRenderLinkedTagOpsEditor();\n}",
        1,
    )

    # prsUpdateSaveResetButtons
    OLD_USB = """function prsUpdateSaveResetButtons() {
  const inputs = __prsConfiguratorHtmlNode.querySelectorAll(".value-changed");
  let dirty = inputs.length > 0;
  if (!dirty) {
    var cn = __prsConfiguratorHtmlNode.querySelector(".currentNode");
    var oc = cn && cn.getAttribute("objectClass");
    if (oc === "prsMethod" && prsInitiatorsDirty()) dirty = true;
  }"""
    NEW_USB = """function prsUpdateSaveResetButtons() {
  const inputs = __prsConfiguratorHtmlNode.querySelectorAll(".value-changed");
  let dirty = inputs.length > 0;
  if (!dirty) {
    var cn = __prsConfiguratorHtmlNode.querySelector(".currentNode");
    var oc = cn && cn.getAttribute("objectClass");
    if (oc === "prsMethod" && prsInitiatorsDirty()) dirty = true;
    if (oc === "prsTag" && typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) dirty = true;
  }"""
    if OLD_USB not in on:
        raise SystemExit("prsUpdateSaveResetButtons head not found")
    on = on.replace(OLD_USB, NEW_USB, 1)

    # resetChanges
    OLD_RST = """resetChanges = () => {
  const elements = __prsConfiguratorHtmlNode.querySelectorAll(`.value-changed`);
  els = [...elements];
  els.map((el) => {
    initValue = el.getAttribute("init-value");
    el.value = initValue;
    el.classList.remove("value-changed");
  });
  prsResetInitiatorsFromInit();
  prsUpdateSaveResetButtons();
};"""
    NEW_RST = """resetChanges = () => {
  const elements = __prsConfiguratorHtmlNode.querySelectorAll(`.value-changed`);
  els = [...elements];
  els.map((el) => {
    initValue = el.getAttribute("init-value");
    el.value = initValue;
    el.classList.remove("value-changed");
  });
  prsResetInitiatorsFromInit();
  try {
    if (typeof prsLinkedTagOpsDirtyFlag !== "undefined") prsLinkedTagOpsDirtyFlag = false;
    if (typeof prsReloadDsLinkedTagOps === "function") prsReloadDsLinkedTagOps();
  } catch (_rs) {}
  prsUpdateSaveResetButtons();
};"""
    if OLD_RST not in on:
        raise SystemExit("resetChanges block not found")
    on = on.replace(OLD_RST, NEW_RST, 1)

    # saveChanges: early exit for linked-only dirty
    OLD_EARLY = """  if (objectClass === "prsTag" && !hasTagAttrChanges && prsConnTagBindDirty) {
    prsSaveConnectorTagBindingAttrsPromise().then(function (ok) {
      if (ok) {
        var nid = $("#div-nodeId").text();
        prsFillTagLinkageUI(nid);
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      }
    });
    return;
  }"""
    NEW_EARLY = """  if (objectClass === "prsTag" && !hasTagAttrChanges && prsConnTagBindDirty) {
    prsSaveConnectorTagBindingAttrsPromise().then(function (ok) {
      if (ok) {
        var nid = $("#div-nodeId").text();
        prsFillTagLinkageUI(nid);
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      }
    });
    return;
  }
  if (objectClass === "prsTag" && !hasTagAttrChanges && !prsConnTagBindDirty && typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
    prsSaveLinkedTagV2Promise().then(function (okL) {
      if (okL) prsLinkedTagOpsDirtyFlag = false;
      prsUpdateSaveResetButtons();
      changeTagDataPanelOnSave();
    });
    return;
  }"""
    if OLD_EARLY not in on:
        raise SystemExit("saveChanges early branch not found")
    on = on.replace(OLD_EARLY, NEW_EARLY, 1)

    # saveChanges success: replace connector branch
    OLD_TAIL = """    if (objectClass === "prsTag" && prsConnTagBindDirty) {
      prsSaveConnectorTagBindingAttrsPromise().then(function (ok2) {
        if (ok2) {
          prsFillTagLinkageUI(nodeId);
        }
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      });
    } else {
      changeTagDataPanelOnSave();
    }"""
    NEW_TAIL = """    if (objectClass === "prsTag" && prsConnTagBindDirty) {
      prsSaveConnectorTagBindingAttrsPromise().then(function (ok2) {
        if (ok2) {
          prsFillTagLinkageUI(nodeId);
        }
        if (typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
          prsSaveLinkedTagV2Promise().then(function (ok3) {
            if (ok3) prsLinkedTagOpsDirtyFlag = false;
            prsUpdateSaveResetButtons();
            changeTagDataPanelOnSave();
          });
        } else {
          prsUpdateSaveResetButtons();
          changeTagDataPanelOnSave();
        }
      });
    } else if (objectClass === "prsTag" && typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
      prsSaveLinkedTagV2Promise().then(function (ok3) {
        if (ok3) prsLinkedTagOpsDirtyFlag = false;
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      });
    } else {
      changeTagDataPanelOnSave();
    }"""
    if OLD_TAIL not in on:
        raise SystemExit("saveChanges tail not found")
    on = on.replace(OLD_TAIL, NEW_TAIL, 1)

    # Clear dirty on populate — two success paths
    marker = "prsLinkedTagActiveOpTab = 0;\n    prsLinkedTagEntryState = prsNormalizeLinkedTagEntry(entry || { tagId: entId, operations: [] }, entId);"
    if marker in on:
        on = on.replace(
            marker,
            "prsLinkedTagActiveOpTab = 0;\n    prsLinkedTagOpsDirtyFlag = false;\n    prsLinkedTagEntryState = prsNormalizeLinkedTagEntry(entry || { tagId: entId, operations: [] }, entId);",
            1,
        )
    marker2 = "prsLinkedTagActiveOpTab = 0;\n    prsLinkedTagEntryState = prsNormalizeLinkedTagEntry({ tagId: entId, operations: [] }, entId);"
    if marker2 in on:
        on = on.replace(
            marker2,
            "prsLinkedTagActiveOpTab = 0;\n    prsLinkedTagOpsDirtyFlag = false;\n    prsLinkedTagEntryState = prsNormalizeLinkedTagEntry({ tagId: entId, operations: [] }, entId);",
            1,
        )

    # Remove prsApplyLinkedTagJsonFromTextarea and prsSaveDsLinkedTagOps blocks
    def remove_function(name: str, s: str) -> str:
        key = f"function {name}("
        if name.startswith("prs"):
            # assignment style
            key2 = f"{name} = function"
            i = s.find(key2)
            if i >= 0:
                key = key2
        i = s.find(key)
        if i < 0:
            return s
        depth = 0
        j = i
        while j < len(s) and s[j] != "{":
            j += 1
        if j >= len(s):
            return s
        depth = 1
        j += 1
        while j < len(s) and depth > 0:
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
            j += 1
        while j < len(s) and s[j] in " \t":
            j += 1
        if j < len(s) and s[j] == ";":
            j += 1
        return s[:i] + s[j:]

    on = remove_function("prsApplyLinkedTagJsonFromTextarea", on)
    on = remove_function("prsSaveDsLinkedTagOps", on)

    cfg["panels"][0]["options"]["onRender"] = on
    cfg["panels"][0]["options"]["html"] = html
    cfg["panels"][0]["options"]["css"] = css
    PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK", PATH)


if __name__ == "__main__":
    main()
