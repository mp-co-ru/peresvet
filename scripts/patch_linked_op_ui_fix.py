#!/usr/bin/env python3
import json
from pathlib import Path

PATH = Path("/home/vovaman/work/projects/peresvet/src/configurator_grafana/Configurator.json")

def main():
    cfg = json.loads(PATH.read_text(encoding="utf-8"))
    on = cfg["panels"][0]["options"]["onRender"]
    css = cfg["panels"][0]["options"]["css"]

    old_flag = "var prsLinkedTagOpsDirtyFlag = false;"
    new_flag = "var prsLinkedTagOpsDirtyFlag = false;\nvar prsLinkedOpFieldInit = null;"
    if "prsLinkedOpFieldInit = null" not in on.split("prsMarkLinkedTagOpsDirty")[0]:
        on = on.replace(old_flag, new_flag, 1)

    mark_end = """function prsMarkLinkedTagOpsDirty() {
  prsLinkedTagOpsDirtyFlag = true;
  if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
}

"""
    insert_block = mark_end + """
function prsLinkedFieldInitKey(oi, part) {
  return String(oi) + "." + part;
}

function prsCaptureLinkedFieldInits() {
  prsLinkedOpFieldInit = {};
  if (!prsLinkedTagEntryState || !prsLinkedTagEntryState.operations) return;
  prsLinkedTagEntryState.operations.forEach(function (op, oi) {
    var a = op.attributes || {};
    var cfg = (a.prsJsonConfigString && typeof a.prsJsonConfigString === "object") ? a.prsJsonConfigString : {};
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "cn")] = prsFirstStr(a.cn) || "";
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "etc")] = String((a.prsEntityTypeCode === 1 || a.prsEntityTypeCode === "1") ? 1 : 0);
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "act")] = (a.prsActive !== false && a.prsActive !== "FALSE") ? "1" : "0";
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "query")] = String(cfg.query || "");
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "tmo")] = String(cfg.timeoutMs != null ? cfg.timeoutMs : 5000);
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "mxr")] = String(cfg.maxRows != null ? cfg.maxRows : 10000);
    prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "ver")] = String(cfg.version != null ? cfg.version : 1);
    var params = Array.isArray(op.parameters) ? op.parameters : [];
    params.forEach(function (p) {
      var cn = prsFirstStr(p.attributes && p.attributes.cn) || "";
      if (!cn) return;
      var cfgp = prsParseJsonMaybe(p.attributes && p.attributes.prsJsonConfigString);
      var jt = cfgp.JSONata != null ? String(cfgp.JSONata) : "";
      prsLinkedOpFieldInit[prsLinkedFieldInitKey(oi, "p." + cn + ".jt")] = jt;
    });
  });
}

function prsLinkedUiSyncDirty(el, oi, part, curStr) {
  if (!el || !prsLinkedOpFieldInit) return;
  var k = prsLinkedFieldInitKey(oi, part);
  var base = prsLinkedOpFieldInit[k];
  if (base === undefined) base = curStr;
  el.classList.toggle("value-changed", String(curStr) !== String(base));
}

"""
    if "function prsLinkedFieldInitKey" not in on:
        on = on.replace(mark_end, insert_block, 1)

    OLD_FILL = """function prsFillLinkedOpParamRowsIntoSlot(oi) {
  var root = __prsConfiguratorHtmlNode;
  var slot = root.getElementById("prs-linked-op-params-slot-" + oi);
  if (!slot || !prsLinkedTagEntryState) return;
  prsSyncLinkedOpParametersFromSql(oi);
  slot.innerHTML = "";
"""
    NEW_FILL = """function prsFillLinkedOpParamRowsIntoSlot(oi, slotEl) {
  var slot = slotEl || __prsConfiguratorHtmlNode.getElementById("prs-linked-op-params-slot-" + oi);
  if (!slot || !prsLinkedTagEntryState) return;
  prsSyncLinkedOpParametersFromSql(oi);
  slot.innerHTML = "";
"""
    if OLD_FILL in on:
        on = on.replace(OLD_FILL, NEW_FILL, 1)

    start = on.find("function prsBuildLinkedOpPaneContent(oi) {")
    end = on.find("\n\n\nfunction prsBuildLinkedParamRow(oi, pi) {")
    if start < 0 or end < 0:
        raise SystemExit(f"pane bounds {start} {end}")

    NEW_PANE = r"""function prsBuildLinkedOpPaneContent(oi) {
  var wrap = document.createElement("div");
  wrap.className = "prs-linked-op-pane-inner w-100";
  var op = prsLinkedTagEntryState.operations[oi];
  var a = op.attributes || {};
  var cfg = (a.prsJsonConfigString && typeof a.prsJsonConfigString === "object") ? a.prsJsonConfigString : {};
  function mkMini(label, controlEl, flexSpec, hug) {
    var ig = document.createElement("div");
    ig.className = "input-group input-group-sm prs-linked-op-mini";
    if (flexSpec) ig.style.flex = flexSpec;
    ig.style.minWidth = 0;
    var sp = document.createElement("span");
    sp.className = "input-group-text prs-input-label prs-linked-op-lbl text-truncate";
    sp.style.maxWidth = "9rem";
    sp.style.flex = "0 0 auto";
    sp.textContent = label;
    sp.title = label;
    ig.appendChild(sp);
    if (controlEl.classList && (controlEl.classList.contains("form-control") || controlEl.classList.contains("form-select"))) {
      ig.appendChild(controlEl);
    } else {
      var w = document.createElement("div");
      w.className = hug ? "d-flex align-items-center justify-content-center flex-shrink-0 prs-linked-op-mini-hug" : "flex-grow-1 min-w-0 d-flex align-items-stretch";
      w.appendChild(controlEl);
      ig.appendChild(w);
    }
    return ig;
  }
  var metaRow = document.createElement("div");
  metaRow.className = "d-flex flex-wrap align-items-end gap-1 mt-1 prs-linked-op-meta-row w-100";
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
  iCn.oninput = function () {
    prsLinkedOpPatch(oi, "cn", iCn.value);
    prsLinkedUiSyncDirty(iCn, oi, "cn", iCn.value);
  };
  iCn.onblur = function () { prsRenderLinkedTagOpsEditor(); };
  metaRow.appendChild(mkMini("\u0418\u043c\u044f (cn)", iCn, "3 1 12rem", false));
  prsLinkedUiSyncDirty(iCn, oi, "cn", iCn.value);
  var sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  var o0 = document.createElement("option"); o0.value = "0"; o0.textContent = "GET (\u0447\u0442\u0435\u043d\u0438\u0435)";
  var o1 = document.createElement("option"); o1.value = "1"; o1.textContent = "SET (\u0437\u0430\u043f\u0438\u0441\u044c)";
  sel.appendChild(o0); sel.appendChild(o1);
  sel.value = String((a.prsEntityTypeCode === 1 || a.prsEntityTypeCode === "1") ? 1 : 0);
  sel.onchange = function () {
    prsLinkedOpPatch(oi, "prsEntityTypeCode", sel.value === "1" ? 1 : 0);
    prsLinkedUiSyncDirty(sel, oi, "etc", sel.value);
    try { if (typeof prsTagIntegRefreshReadPanel === "function") prsTagIntegRefreshReadPanel(); } catch (_e2) {}
  };
  metaRow.appendChild(mkMini("\u0422\u0438\u043f", sel, "2 1 9rem", false));
  prsLinkedUiSyncDirty(sel, oi, "etc", sel.value);
  var fcAct = document.createElement("span");
  fcAct.className = "form-control form-control-sm d-flex align-items-center justify-content-center py-0 prs-linked-op-act-cell";
  fcAct.style.minHeight = "calc(1.5em + 0.5rem + 2px)";
  var cb = document.createElement("input");
  cb.type = "checkbox";
  cb.className = "prs-tag-data-toggle-input";
  cb.checked = a.prsActive !== false && a.prsActive !== "FALSE";
  cb.onchange = function () {
    prsLinkedOpPatch(oi, "prsActive", cb.checked);
    prsLinkedUiSyncDirty(fcAct, oi, "act", cb.checked ? "1" : "0");
  };
  fcAct.appendChild(cb);
  metaRow.appendChild(mkMini("\u0410\u043a\u0442.", fcAct, "0 0 auto", true));
  prsLinkedUiSyncDirty(fcAct, oi, "act", cb.checked ? "1" : "0");
  var iTm = document.createElement("input");
  iTm.type = "number";
  iTm.className = "form-control form-control-sm";
  iTm.step = "1";
  iTm.value = String(cfg.timeoutMs != null ? cfg.timeoutMs : 5000);
  iTm.oninput = function () {
    var n = parseFloat(iTm.value);
    prsLinkedOpPatchJson(oi, "timeoutMs", isFinite(n) ? n : 5000);
    prsLinkedUiSyncDirty(iTm, oi, "tmo", String(isFinite(n) ? n : 5000));
  };
  metaRow.appendChild(mkMini("t/o ms", iTm, "1 1 5.5rem", false));
  prsLinkedUiSyncDirty(iTm, oi, "tmo", iTm.value);
  var iMr = document.createElement("input");
  iMr.type = "number";
  iMr.className = "form-control form-control-sm";
  iMr.step = "1";
  iMr.value = String(cfg.maxRows != null ? cfg.maxRows : 10000);
  iMr.oninput = function () {
    var n = parseFloat(iMr.value);
    prsLinkedOpPatchJson(oi, "maxRows", isFinite(n) ? n : 10000);
    prsLinkedUiSyncDirty(iMr, oi, "mxr", String(isFinite(n) ? n : 10000));
  };
  metaRow.appendChild(mkMini("maxR", iMr, "1 1 5rem", false));
  prsLinkedUiSyncDirty(iMr, oi, "mxr", iMr.value);
  var iVer = document.createElement("input");
  iVer.type = "number";
  iVer.className = "form-control form-control-sm";
  iVer.step = "1";
  iVer.value = String(cfg.version != null ? cfg.version : 1);
  iVer.oninput = function () {
    var n = parseFloat(iVer.value);
    prsLinkedOpPatchJson(oi, "version", isFinite(n) ? n : 1);
    prsLinkedUiSyncDirty(iVer, oi, "ver", String(isFinite(n) ? n : 1));
  };
  metaRow.appendChild(mkMini("ver", iVer, "0 0 4.25rem", false));
  prsLinkedUiSyncDirty(iVer, oi, "ver", iVer.value);
  wrap.appendChild(metaRow);
  var taq = document.createElement("textarea");
  taq.className = "form-control form-control-sm prs-mono flex-grow-1";
  taq.rows = 5;
  taq.value = cfg.query || "";
  taq.oninput = function () {
    prsLinkedOpPatchJson(oi, "query", taq.value);
    prsLinkedUiSyncDirty(taq, oi, "query", taq.value);
  };
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
  prsLinkedUiSyncDirty(taq, oi, "query", taq.value);
  var slot = document.createElement("div");
  slot.id = "prs-linked-op-params-slot-" + oi;
  slot.className = "prs-linked-sql-params-slot";
  wrap.appendChild(slot);
  prsFillLinkedOpParamRowsIntoSlot(oi, slot);
  return wrap;
}"""
    on = on[:start] + NEW_PANE + on[end:]

    old_jt = """  iJt.oninput = function () {
    prsLinkedParamPatchJson(oi, pi, "JSONata", iJt.value);
    try { if (typeof prsTagIntegRefreshReadPanel === "function") prsTagIntegRefreshReadPanel(); } catch (_e3) {}
  };
  box.appendChild(prsLinkedMkInputGroupRow("JSONata", iJt));
  return box;
}"""
    new_jt = """  iJt.oninput = function () {
    prsLinkedParamPatchJson(oi, pi, "JSONata", iJt.value);
    var cnk = prsFirstStr(pa.cn) || String(pi);
    prsLinkedUiSyncDirty(iJt, oi, "p." + cnk + ".jt", iJt.value);
    try { if (typeof prsTagIntegRefreshReadPanel === "function") prsTagIntegRefreshReadPanel(); } catch (_e3) {}
  };
  box.appendChild(prsLinkedMkInputGroupRow("JSONata", iJt));
  (function () {
    var cnk2 = prsFirstStr(pa.cn) || String(pi);
    prsLinkedUiSyncDirty(iJt, oi, "p." + cnk2 + ".jt", iJt.value);
  })();
  return box;
}"""
    if old_jt not in on:
        raise SystemExit("param row block not found")
    on = on.replace(old_jt, new_jt, 1)

    # populate: sync all SQL params + capture + render (both success paths)
    needle = "prsRenderLinkedTagOpsEditor();\n    try { if (typeof prsTagIntegRefreshReadPanel === \"function\") prsTagIntegRefreshReadPanel(); } catch (_rf) {}\n    if (typeof prsSyncRightPlaceholder"
    repl = """for (var _si = 0; _si < (prsLinkedTagEntryState.operations || []).length; _si++) { prsSyncLinkedOpParametersFromSql(_si); }
    prsCaptureLinkedFieldInits();
    prsRenderLinkedTagOpsEditor();
    try { if (typeof prsTagIntegRefreshReadPanel === \"function\") prsTagIntegRefreshReadPanel(); } catch (_rf) {}\n    if (typeof prsSyncRightPlaceholder"""
    cnt = on.count(needle)
    if cnt >= 1:
        on = on.replace(needle, repl, cnt)
        print("populate inject", cnt)
    else:
        print("WARN needle not found for populate")

    # hide panel: clear field init
    hide_snip = "prsLinkedTagEntryState = null;"
    hide_repl = "prsLinkedTagEntryState = null;\n    prsLinkedOpFieldInit = null;"
    if hide_snip in on and on.count(hide_repl) < 2:
        # only in prsHideTagIntegrationalPanel - be careful
        idx = on.find("function prsHideTagIntegrationalPanel")
        chunk = on[idx : idx + 900]
        if "prsLinkedOpFieldInit = null" not in chunk:
            on = on.replace(
                """    prsLinkedTagEntryState = null;
    var ed = __prsConfiguratorHtmlNode.getElementById("prs-ds-linked-tag-ops-editor");""",
                """    prsLinkedTagEntryState = null;
    prsLinkedOpFieldInit = null;
    var ed = __prsConfiguratorHtmlNode.getElementById("prs-ds-linked-tag-ops-editor");""",
                1,
            )

    # save v2 success: refresh baselines
    save_ok = """        resolve(ok);
      })
      .catch(function () {"""
    # find prsSaveLinkedTagV2Promise resolve(ok) before catch
    old_save_tail = """        if (!ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0438 linkedTags (v2)", false);
        } else {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "linkedTags \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d.", true);
        }
        resolve(ok);"""
    new_save_tail = """        if (!ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0438 linkedTags (v2)", false);
        } else {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "linkedTags \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d.", true);
          try {
            for (var _sj = 0; _sj < (prsLinkedTagEntryState.operations || []).length; _sj++) { prsSyncLinkedOpParametersFromSql(_sj); }
            prsCaptureLinkedFieldInits();
            prsRenderLinkedTagOpsEditor();
          } catch (_sok) {}
        }
        resolve(ok);"""
    if old_save_tail in on:
        on = on.replace(old_save_tail, new_save_tail, 1)
    else:
        print("WARN save tail not found")

    CSS_ADD = """

/* Операции v2: строка полей без «расползания», чекбокс не забирает ширину */
.prs-linked-op-meta-row {
  width: 100%;
  box-sizing: border-box;
  margin-left: 0 !important;
}
.prs-linked-op-mini {
  max-width: 100%;
}
.prs-linked-op-mini .form-control,
.prs-linked-op-mini .form-select {
  min-width: 0;
}
.prs-linked-op-mini-hug {
  flex: 0 0 auto !important;
  width: auto !important;
  max-width: 3.25rem !important;
  min-width: 0 !important;
}
.prs-linked-op-act-cell {
  width: 100%;
  max-width: 2.75rem;
}
.w-100 { width: 100% !important; }

/* Подсветка изменённых полей в панели привязки тега */
#prs-ds-linked-tag-panel .input-group > .form-control.value-changed,
#prs-ds-linked-tag-panel .input-group > .form-select.value-changed {
  box-shadow: inset 0 0 0 2px rgba(44, 112, 127, 0.95) !important;
  background-color: rgba(230, 242, 244, 0.55) !important;
  z-index: 2;
  position: relative;
}
"""
    if ".prs-linked-op-mini-hug" not in css:
        css = css + CSS_ADD

    cfg["panels"][0]["options"]["onRender"] = on
    cfg["panels"][0]["options"]["css"] = css
    PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(PATH.read_text(encoding="utf-8"))
    print("OK")


if __name__ == "__main__":
    main()
