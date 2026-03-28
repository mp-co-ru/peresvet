#!/usr/bin/env python3
"""Patch Configurator.json: merge tag search into DataGet card + multi tagId chips."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "Configurator.json"


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    opts = data["panels"][0]["options"]
    h = opts["html"]
    on = opts["onRender"]
    css = opts.get("css", "")

    needle = '<div class="d-flex flex-wrap align-items-start w-100 border-bottom pb-2 mb-2 prs-method-param-row" prsIndex="0" id="span-parameter-0">'
    i0 = h.find(needle)
    if i0 < 0:
        raise SystemExit("span-parameter-0 not found")
    idx = h.find("i-deleteParameter-0", i0)
    idx = h.find("</button>", idx)
    idx = h.find("</div>", idx)
    idx2 = h.find("</div>", idx + 1)
    old_block = h[i0 : idx2 + len("</div>")]

    k = old_block.find('<div class="d-flex flex-wrap gap-3 mb-2">')
    if k < 0:
        raise SystemExit("format row not found in param block")
    tail = old_block[k:]

    t7, t8, t9, t10, t11 = "\t" * 7, "\t" * 8, "\t" * 9, "\t" * 10, "\t" * 11

    new_block = (
        needle
        + "\n"
        + t8
        + '<div class="w-100 d-flex flex-wrap align-items-end justify-content-between gap-2 mb-2 prs-method-param-head">\n'
        + t9
        + '<div class="d-flex flex-wrap gap-2 flex-grow-1 min-w-0">\n'
        + t10
        + '<div class="col-6 col-sm-auto" style="min-width:4.5rem">\n'
        + t11
        + '<div class="text-muted smaller mb-0">Индекс</div>\n'
        + t11
        + '<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-0"/>\n'
        + t10
        + "</div>\n"
        + t10
        + '<div class="col-6 col-sm min-w-0 flex-grow-1" style="min-width:8rem">\n'
        + t11
        + '<div class="text-muted smaller mb-0">Имя</div>\n'
        + t11
        + '<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-0"/>\n'
        + t10
        + "</div>\n"
        + t9
        + "</div>\n"
        + t9
        + '<div class="flex-shrink-0">\n'
        + t10
        + '<button type="button" id="but-deleteParameter-0" class="btn btn-sm btn-danger" onclick="deleteParameter(event);" title="Удалить параметр">\n'
        + t11
        + '<span><i class="fa-solid fa-minus" id="i-deleteParameter-0"></i></span>\n'
        + t10
        + "</button>\n"
        + t9
        + "</div>\n"
        + t8
        + "</div>\n"
        + t8
        + '<div class="w-100 min-w-0 mb-1 prs-method-param-dg-host">\n'
        + t9
        + '<div class="prs-method-param-dg border rounded p-2 bg-light">\n'
        + t10
        + '<div class="smaller text-muted mb-2"><strong>GET /v1/data/</strong> — тело как <code>DataGet</code> (несколько <code>tagId</code> в одном запросе). При запуске метода платформа подставляет <strong>finish</strong>.</div>\n'
        + t10
        + '<div class="prs-method-param-tags-section mb-2 pb-2 border-bottom border-secondary-subtle">\n'
        + t11
        + '<div class="text-muted smaller mb-1">Теги</div>\n'
        + t11
        + '<div class="smaller text-muted mb-2">Поиск по дереву: у результата кнопка <i class="fa-solid fa-anchor" aria-hidden="true"></i> <strong>добавляет</strong> тег в список (дубликаты не добавляются).</div>\n'
        + t11
        + '<input type="hidden" id="input-parameter-tagId-0" value=""/>\n'
        + t11
        + '<div class="input-group input-group-sm">\n'
        + t11
        + "\t"
        + '<input type="search" class="form-control" id="input-parameter-tagSearch-0" placeholder="Имя, путь или id…" autocomplete="off"/>\n'
        + t11
        + "\t"
        + '<button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-0" title="Найти">Найти</button>\n'
        + t11
        + "</div>\n"
        + t11
        + '<div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-0"></div>\n'
        + t11
        + '<div id="div-parameter-tagChips-0" class="prs-param-tag-chips d-flex flex-wrap gap-1 mt-2 align-items-center"></div>\n'
        + t11
        + '<div class="prs-param-tag-pick-label small text-muted mt-1 d-none" id="span-parameter-tagPick-0"></div>\n'
        + t10
        + "</div>\n"
        + t10
        + '<div class="smaller fw-semibold text-muted mb-2">Поля запроса</div>\n'
        + tail
    )

    if h.count(old_block) != 1:
        raise SystemExit(f"expected 1 old param block, got {h.count(old_block)}")
    opts["html"] = h.replace(old_block, new_block, 1)

    append_start = on.find('$("#div-list-parameters").append(`')
    append_end = on.find("`);\n\n    level = newLevel", append_start)
    if append_start < 0 or append_end < 0:
        raise SystemExit("addParameter append not found")
    old_append = on[append_start : append_end + 3]

    new_append = r"""$("#div-list-parameters").append(`
      <div class="d-flex flex-wrap align-items-start w-100 border-bottom pb-2 mb-2 prs-method-param-row" prsIndex="${newLevel}" id="span-parameter-${newLevel}">
        <div class="w-100 d-flex flex-wrap align-items-end justify-content-between gap-2 mb-2 prs-method-param-head">
          <div class="d-flex flex-wrap gap-2 flex-grow-1 min-w-0">
            <div class="col-6 col-sm-auto" style="min-width:4.5rem">
              <div class="text-muted smaller mb-0">Индекс</div>
              <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-${newLevel}"/>
            </div>
            <div class="col-6 col-sm min-w-0 flex-grow-1" style="min-width:8rem">
              <div class="text-muted smaller mb-0">Имя</div>
              <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-${newLevel}"/>
            </div>
          </div>
          <div class="flex-shrink-0">
            <button type="button" id="but-deleteParameter-${newLevel}" class="btn btn-sm btn-danger" onclick="deleteParameter(event);" title="Удалить параметр">
              <span><i class="fa-solid fa-minus" id="i-deleteParameter-${newLevel}"></i></span>
            </button>
          </div>
        </div>
        <div class="w-100 min-w-0 mb-1 prs-method-param-dg-host">
          <div class="prs-method-param-dg border rounded p-2 bg-light">
            <div class="smaller text-muted mb-2"><strong>GET /v1/data/</strong> — <code>DataGet</code>, несколько <code>tagId</code>. Платформа подставляет <strong>finish</strong>.</div>
            <div class="prs-method-param-tags-section mb-2 pb-2 border-bottom border-secondary-subtle">
              <div class="text-muted smaller mb-1">Теги</div>
              <div class="smaller text-muted mb-2">Поиск → <i class="fa-solid fa-anchor" aria-hidden="true"></i> <strong>добавляет</strong> тег (без дубликатов).</div>
              <input type="hidden" id="input-parameter-tagId-${newLevel}" value=""/>
              <div class="input-group input-group-sm">
                <input type="search" class="form-control" id="input-parameter-tagSearch-${newLevel}" placeholder="Имя, путь или id…" autocomplete="off"/>
                <button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-${newLevel}" title="Найти">Найти</button>
              </div>
              <div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-${newLevel}"></div>
              <div id="div-parameter-tagChips-${newLevel}" class="prs-param-tag-chips d-flex flex-wrap gap-1 mt-2 align-items-center"></div>
              <div class="prs-param-tag-pick-label small text-muted mt-1 d-none" id="span-parameter-tagPick-${newLevel}"></div>
            </div>
            <div class="smaller fw-semibold text-muted mb-2">Поля запроса</div>
            <div class="d-flex flex-wrap gap-3 mb-2">
              <label class="form-check smaller mb-0"><input type="checkbox" class="form-check-input" id="input-param-dg-format-${newLevel}" onchange="prsMethodParamOnBuilderChange(${newLevel})"> format</label>
              <label class="form-check smaller mb-0"><input type="checkbox" class="form-check-input" id="input-param-dg-actual-${newLevel}" onchange="prsMethodParamOnBuilderChange(${newLevel})"> actual</label>
            </div>
            <div class="row g-1 mb-1">
              <div class="col-6 col-lg-3"><label class="form-label smaller mb-0 text-muted">start</label><input class="form-control form-control-sm" id="input-param-dg-start-${newLevel}" placeholder="опционально" oninput="prsMethodParamOnBuilderChange(${newLevel})"/></div>
              <div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">maxCount</label><input type="number" class="form-control form-control-sm" id="input-param-dg-maxCount-${newLevel}" oninput="prsMethodParamOnBuilderChange(${newLevel})"/></div>
              <div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">count</label><input type="number" class="form-control form-control-sm" id="input-param-dg-count-${newLevel}" oninput="prsMethodParamOnBuilderChange(${newLevel})"/></div>
              <div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">timeStep</label><input type="number" class="form-control form-control-sm" id="input-param-dg-timeStep-${newLevel}" oninput="prsMethodParamOnBuilderChange(${newLevel})"/></div>
            </div>
            <div class="mb-1">
              <label class="form-label smaller mb-0 text-muted">value (строка или JSON)</label>
              <input class="form-control form-control-sm prs-mono" id="input-param-dg-value-${newLevel}" placeholder="опционально" oninput="prsMethodParamOnBuilderChange(${newLevel})"/>
            </div>
            <div class="mb-1">
              <label class="form-label smaller mb-0 text-muted">params (JSON)</label>
              <textarea class="form-control form-control-sm prs-mono" rows="2" id="textarea-param-dg-params-${newLevel}" placeholder="{}" oninput="prsMethodParamOnBuilderChange(${newLevel})"></textarea>
            </div>
            <div class="input-group input-group-sm mt-1">
              <span class="input-group-text smaller text-wrap">URL (без finish)</span>
              <input type="text" readonly class="form-control form-control-sm prs-mono text-truncate" id="input-parameter-dataUrl-preview-${newLevel}"/>
            </div>
            <div class="d-flex flex-wrap gap-1 mt-1">
              <button type="button" class="btn btn-sm btn-outline-primary" onclick="prsMethodParamTestGet(${newLevel})">Пробный запрос</button>
            </div>
            <details class="mt-2 smaller">
              <summary class="user-select-none">JSON (prsJsonConfigString)</summary>
              <textarea class="form-control form-control-sm prs-mono mt-1" rows="5" prsAttribute="parameter" autocomplete="off" id="input-parameter-prsJsonConfigString-${newLevel}" onchange="onInputChange(event);" onblur="prsMethodParamOnJsonBlur(${newLevel})">{}</textarea>
            </details>
            <pre class="smaller bg-white border rounded p-2 mt-1 mb-0 d-none text-break prs-param-dg-test-out" id="pre-parameter-dg-test-${newLevel}"></pre>
          </div>
        </div>
      </div>
    `)"""

    if on.count(old_append) != 1:
        raise SystemExit(f"expected 1 append template, got {on.count(old_append)}")
    on = on.replace(old_append, new_append, 1)

    insert_after = """  return x;
}

function prsMethodParamApplyJsonToBuilderFields(level, raw) {"""

    insert_block = """  return x;
}

function prsMethodParamResolveTagRow(level, tagId) {
  var rows = (window.prsParamPickerCatalog && window.prsParamPickerCatalog[level]) || [];
  var id = String(tagId || "");
  var found = null;
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].id) === id) { found = rows[i]; break; }
  }
  return found || { id: id, cn: "", path: "" };
}

function prsMethodParamDismissTagSearch(level) {
  const res = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagResults-" + level);
  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  if (res) {
    res.classList.add("d-none");
    res.innerHTML = "";
  }
  if (inp) inp.value = "";
}

function prsMethodParamRenderTagChips(level, tagIds) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagChips-" + level);
  const hint = __prsConfiguratorHtmlNode.getElementById("span-parameter-tagPick-" + level);
  const hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  if (!box) return;
  var ids = [];
  if (Array.isArray(tagIds)) ids = tagIds.map(String).filter(Boolean);
  else if (tagIds != null && String(tagIds) !== "") ids = [String(tagIds)];
  box.innerHTML = "";
  if (hint) {
    hint.innerHTML = "";
    hint.classList.add("d-none");
  }
  if (hid) hid.value = ids.length ? ids[0] : "";
  ids.forEach(function (tid) {
    var row = prsMethodParamResolveTagRow(level, tid);
    var chip = document.createElement("span");
    chip.className = "badge bg-light text-dark border d-inline-flex align-items-center gap-1 prs-param-tag-chip";
    chip.setAttribute("data-prs-tag-id", tid);
    var label = document.createElement("span");
    label.className = "prs-param-tag-chip-label text-truncate";
    label.style.maxWidth = "18rem";
    var path = (row.path && String(row.path).trim()) ? row.path : "";
    var cn = row.cn || "";
    label.title = path ? path + "\\n" + tid : tid;
    label.textContent = path ? path : (cn ? cn + " · " + tid : tid);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-close btn-close-sm";
    btn.setAttribute("aria-label", "Удалить");
    btn.addEventListener("click", function () {
      prsMethodParamRemoveTagFromParam(level, tid);
    });
    chip.appendChild(label);
    chip.appendChild(btn);
    box.appendChild(chip);
  });
  if (hint && ids.length) {
    var rows = (window.prsParamPickerCatalog && window.prsParamPickerCatalog[level]) || [];
    var missing = ids.filter(function (id) {
      for (var j = 0; j < rows.length; j++) if (String(rows[j].id) === id) return false;
      return true;
    });
    if (missing.length) {
      hint.classList.remove("d-none");
      hint.textContent = "Часть тегов нет в текущем каталоге поиска — отображается id; данные запроса валидны.";
    }
  }
}

function prsMethodParamRemoveTagFromParam(level, tagId) {
  var ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  if (!ta) return;
  var base = {};
  try { base = JSON.parse(ta.value || "{}"); } catch (e0) { return; }
  if (typeof base !== "object" || base === null || Array.isArray(base)) base = {};
  var ids = [];
  if (Array.isArray(base.tagId)) ids = base.tagId.map(String).filter(Boolean);
  else if (base.tagId != null && String(base.tagId) !== "") ids = [String(base.tagId)];
  var rm = String(tagId);
  ids = ids.filter(function (x) { return x !== rm; });
  if (ids.length) base.tagId = ids;
  else delete base.tagId;
  var norm = prsMethodParamNormalizeConfig(base);
  ta.value = JSON.stringify(norm, null, "\\t");
  prsMethodParamApplyJsonToBuilderFields(level, norm);
  var initv = ta.getAttribute("init-value");
  if (initv != null && ta.value !== initv) ta.classList.add("value-changed");
  else ta.classList.remove("value-changed");
  var pre = __prsConfiguratorHtmlNode.getElementById("pre-parameter-dg-test-" + level);
  if (pre) pre.classList.add("d-none");
  prsUpdateSaveResetButtons();
}



function prsMethodParamApplyJsonToBuilderFields(level, raw) {"""

    if insert_after not in on:
        raise SystemExit("insert anchor not found")
    on = on.replace(insert_after, insert_block, 1)

    old_apply = """function prsMethodParamApplyJsonToBuilderFields(level, raw) {
  var o = prsMethodParamNormalizeConfig(raw);
  var fmt = __prsConfiguratorHtmlNode.getElementById("input-param-dg-format-" + level);
  var act = __prsConfiguratorHtmlNode.getElementById("input-param-dg-actual-" + level);
  var st = __prsConfiguratorHtmlNode.getElementById("input-param-dg-start-" + level);
  var mc = __prsConfiguratorHtmlNode.getElementById("input-param-dg-maxCount-" + level);
  var cnt = __prsConfiguratorHtmlNode.getElementById("input-param-dg-count-" + level);
  var ts = __prsConfiguratorHtmlNode.getElementById("input-param-dg-timeStep-" + level);
  var val = __prsConfiguratorHtmlNode.getElementById("input-param-dg-value-" + level);
  var prm = __prsConfiguratorHtmlNode.getElementById("textarea-param-dg-params-" + level);
  if (fmt) fmt.checked = !!o.format;
  if (act) act.checked = !!o.actual;
  if (st) st.value = o.start != null ? String(o.start) : "";
  if (mc) mc.value = o.maxCount != null ? String(o.maxCount) : "";
  if (cnt) cnt.value = o.count != null ? String(o.count) : "";
  if (ts) ts.value = o.timeStep != null ? String(o.timeStep) : "";
  if (val) {
    if (o.value !== undefined) {
      val.value = typeof o.value === "object" ? JSON.stringify(o.value) : String(o.value);
    } else val.value = "";
  }
  if (prm) prm.value = o.params && Object.keys(o.params).length ? JSON.stringify(o.params, null, 2) : "";
  var hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  if (hid && o.tagId && o.tagId.length) hid.value = o.tagId[0];
  prsMethodParamUpdateUrlPreview(level);
}"""

    new_apply = """function prsMethodParamApplyJsonToBuilderFields(level, raw) {
  var o = prsMethodParamNormalizeConfig(raw);
  var fmt = __prsConfiguratorHtmlNode.getElementById("input-param-dg-format-" + level);
  var act = __prsConfiguratorHtmlNode.getElementById("input-param-dg-actual-" + level);
  var st = __prsConfiguratorHtmlNode.getElementById("input-param-dg-start-" + level);
  var mc = __prsConfiguratorHtmlNode.getElementById("input-param-dg-maxCount-" + level);
  var cnt = __prsConfiguratorHtmlNode.getElementById("input-param-dg-count-" + level);
  var ts = __prsConfiguratorHtmlNode.getElementById("input-param-dg-timeStep-" + level);
  var val = __prsConfiguratorHtmlNode.getElementById("input-param-dg-value-" + level);
  var prm = __prsConfiguratorHtmlNode.getElementById("textarea-param-dg-params-" + level);
  if (fmt) fmt.checked = !!o.format;
  if (act) act.checked = !!o.actual;
  if (st) st.value = o.start != null ? String(o.start) : "";
  if (mc) mc.value = o.maxCount != null ? String(o.maxCount) : "";
  if (cnt) cnt.value = o.count != null ? String(o.count) : "";
  if (ts) ts.value = o.timeStep != null ? String(o.timeStep) : "";
  if (val) {
    if (o.value !== undefined) {
      val.value = typeof o.value === "object" ? JSON.stringify(o.value) : String(o.value);
    } else val.value = "";
  }
  if (prm) prm.value = o.params && Object.keys(o.params).length ? JSON.stringify(o.params, null, 2) : "";
  var hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  if (hid) hid.value = o.tagId && o.tagId.length ? o.tagId[0] : "";
  prsMethodParamRenderTagChips(level, o.tagId || []);
  prsMethodParamDismissTagSearch(level);
  prsMethodParamUpdateUrlPreview(level);
}"""

    if on.count(old_apply) != 1:
        raise SystemExit(f"ApplyJson block count {on.count(old_apply)}")
    on = on.replace(old_apply, new_apply, 1)

    old_collect = """function prsMethodParamCollectFromBuilder(level) {
  var hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  var tagId = (hid && hid.value || "").trim();
  var o = {};
  if (tagId) o.tagId = [tagId];"""

    new_collect = """function prsMethodParamCollectFromBuilder(level) {
  var o = {};
  var chipBox = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagChips-" + level);
  var ids = [];
  if (chipBox) {
    chipBox.querySelectorAll("[data-prs-tag-id]").forEach(function (el) {
      ids.push(el.getAttribute("data-prs-tag-id"));
    });
  }
  if (ids.length) o.tagId = ids;"""

    if on.count(old_collect) != 1:
        raise SystemExit(f"Collect block count {on.count(old_collect)}")
    on = on.replace(old_collect, new_collect, 1)

    old_setui = """function prsMethodParamSetTagPickUI(level, row) {
  const hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  const span = __prsConfiguratorHtmlNode.getElementById("span-parameter-tagPick-" + level);
  const res = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagResults-" + level);
  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  if (hid) hid.value = row.id;
  if (span) {
    span.className = "prs-param-tag-pick-label small text-muted mt-1";
    span.innerHTML = "";
    if (row.path && String(row.path).trim()) {
      var pl = document.createElement("div");
      pl.className = "prs-pick-path";
      pl.textContent = row.path;
      span.appendChild(pl);
    }
    var meta = document.createElement("div");
    meta.className = "prs-pick-meta";
    meta.textContent = (row.cn || "") + " (" + row.id + ")";
    span.appendChild(meta);
  }
  if (res) {
    res.classList.add("d-none");
    res.innerHTML = "";
  }
  if (inp) inp.value = "";
}"""

    new_setui = """function prsMethodParamSetTagPickUI(level, row) {
  prsMethodParamDismissTagSearch(level);
}"""

    if on.count(old_setui) != 1:
        raise SystemExit(f"SetTagPickUI count {on.count(old_setui)}")
    on = on.replace(old_setui, new_setui, 1)

    old_pick = """function prsApplyParameterTagPick(level, row, silentInit) {
  prsMethodParamSetTagPickUI(level, row);
  const ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  if (ta) {
    var base = {};
    try { base = JSON.parse(ta.value || "{}"); } catch (e0) { base = {}; }
    if (typeof base !== "object" || base === null || Array.isArray(base)) base = {};
    base.tagId = [row.id];
    var norm = prsMethodParamNormalizeConfig(base);
    const jsonStr = JSON.stringify(norm, null, "\\t");
    ta.value = jsonStr;
    prsMethodParamApplyJsonToBuilderFields(level, norm);
    if (silentInit) ta.setAttribute("init-value", jsonStr);
    else ta.classList.add("value-changed");
  }
  if (!silentInit) prsUpdateSaveResetButtons();
}"""

    new_pick = """function prsApplyParameterTagPick(level, row, silentInit) {
  const ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  if (ta) {
    var base = {};
    try { base = JSON.parse(ta.value || "{}"); } catch (e0) { base = {}; }
    if (typeof base !== "object" || base === null || Array.isArray(base)) base = {};
    var ids = [];
    if (Array.isArray(base.tagId)) ids = base.tagId.map(String).filter(Boolean);
    else if (base.tagId != null && String(base.tagId) !== "") ids = [String(base.tagId)];
    var rid = String(row.id);
    if (ids.indexOf(rid) < 0) ids.push(rid);
    base.tagId = ids;
    var norm = prsMethodParamNormalizeConfig(base);
    const jsonStr = JSON.stringify(norm, null, "\\t");
    ta.value = jsonStr;
    prsMethodParamApplyJsonToBuilderFields(level, norm);
    if (silentInit) ta.setAttribute("init-value", jsonStr);
    else ta.classList.add("value-changed");
  }
  prsMethodParamDismissTagSearch(level);
  if (!silentInit) prsUpdateSaveResetButtons();
}"""

    if on.count(old_pick) != 1:
        raise SystemExit(f"ApplyParameterTagPick count {on.count(old_pick)}")
    on = on.replace(old_pick, new_pick, 1)

    old_prepare_tail = """    let tagId;
    if (Array.isArray(config.tagId)) tagId = config.tagId[0];
    else tagId = config.tagId;
    var norm = prsMethodParamNormalizeConfig(config);
    var normStr = JSON.stringify(norm, null, "\\t");
    $(`#input-parameter-prsIndex-${level}`).val(index).attr("init-value", String(index));
    $(`#input-parameter-cn-${level}`).val(name).attr("init-value", name);
    var ta0 = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
    if (ta0) {
      ta0.value = normStr;
      ta0.setAttribute("init-value", normStr);
    }
    prsMethodParamApplyJsonToBuilderFields(level, norm);
    const row = rows.find((r) => r.id === tagId);
    if (row) prsMethodParamSetTagPickUI(level, row);
    else if (tagId) {
      const hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
      const span = __prsConfiguratorHtmlNode.getElementById("span-parameter-tagPick-" + level);
      if (hid) { hid.value = tagId; hid.setAttribute("init-value", tagId); }
      if (span) {
        span.className = "prs-param-tag-pick-label small text-muted mt-1";
        span.innerHTML = "";
        var note = document.createElement("div");
        note.className = "prs-pick-saved-note";
        note.textContent = "Сохранённый тег (нет в текущем поиске):";
        span.appendChild(note);
        var meta = document.createElement("div");
        meta.className = "prs-pick-meta";
        meta.textContent = tagId;
        span.appendChild(meta);
      }
    }
    prsMethodParamUpdateUrlPreview(level);"""

    new_prepare_tail = """    var norm = prsMethodParamNormalizeConfig(config);
    var normStr = JSON.stringify(norm, null, "\\t");
    $(`#input-parameter-prsIndex-${level}`).val(index).attr("init-value", String(index));
    $(`#input-parameter-cn-${level}`).val(name).attr("init-value", name);
    var ta0 = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
    if (ta0) {
      ta0.value = normStr;
      ta0.setAttribute("init-value", normStr);
    }
    prsMethodParamApplyJsonToBuilderFields(level, norm);
    const hid0 = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
    if (hid0) {
      var first = norm.tagId && norm.tagId.length ? norm.tagId[0] : "";
      hid0.setAttribute("init-value", first || "");
    }
    prsMethodParamUpdateUrlPreview(level);"""

    if on.count(old_prepare_tail) != 1:
        raise SystemExit(f"prepare tail count {on.count(old_prepare_tail)}")
    on = on.replace(old_prepare_tail, new_prepare_tail, 1)

    on = on.replace(
        'pre.textContent = "Укажите тег (tagId).";',
        'pre.textContent = "Добавьте хотя бы один тег (tagId).";',
        1,
    )

    on = on.replace(
        'btn.title = "Выбрать этот тег";',
        'btn.title = "Добавить тег в запрос";',
        1,
    )

    css_add = (
        "\n/* Чипы тегов в параметре метода */\n"
        ".prs-param-tag-chips .prs-param-tag-chip { max-width: 100%; font-weight: 500; }\n"
        ".prs-param-tag-chip .btn-close { transform: scale(0.72); opacity: 0.7; }\n"
        ".prs-method-param-head { min-width: 0; }\n"
    )
    if "prs-param-tag-chip" not in css:
        opts["css"] = css + css_add

    opts["onRender"] = on

    # validate JSON round-trip
    out = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(out)
    PATH.write_text(out + "\n", encoding="utf-8")
    print("OK:", PATH)


if __name__ == "__main__":
    main()
