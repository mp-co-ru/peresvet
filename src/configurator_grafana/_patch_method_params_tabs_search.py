#!/usr/bin/env python3
"""Configurator: param tabs, unified tag search (loupe + ⚓ glyph), compact layout, fix addParameter reset."""
import json
from pathlib import Path

P = Path(__file__).resolve().parent / "Configurator.json"


def main() -> None:
    d = json.loads(P.read_text(encoding="utf-8"))
    opts = d["panels"][0]["options"]
    h = opts["html"]
    on = opts["onRender"]
    css = opts.get("css", "")

    _dpi = h.find('id="div-parameters">')
    _fc = h.find('\t\t\t\t<div class="form-control">', _dpi)
    _old_row_start = h.find(
        '\t\t\t\t\t\t\t<div class="d-flex flex-wrap align-items-start w-100 border-bottom pb-2 mb-2 prs-method-param-row"',
        _fc,
    )
    if _dpi < 0 or _fc < 0 or _old_row_start < 0:
        raise SystemExit("div-parameters / form-control / param row0 not found")
    _old_row_gt = h.find(">", _old_row_start) + 1
    OLD_FORM_START = h[_fc:_old_row_gt]

    NEW_FORM_START = """\t\t\t\t<div class="form-control p-2">
\t\t\t\t\t<p class="smaller text-muted mb-2">Параметры передаются в метод по порядку индекса. Каждая <strong>закладка</strong> — имя, теги и тело <code>DataGet</code> для <code>GET /v1/data/</code>.</p>
\t\t\t\t\t<div id="div-list-parameters" class="prs-method-params-wrap w-100">
\t\t\t\t\t\t<div class="d-flex align-items-end gap-2 flex-wrap mb-2 prs-method-param-toolbar">
\t\t\t\t\t\t\t<div class="flex-shrink-0">
\t\t\t\t\t\t\t\t<button id="but-addParameter-0" class="btn btn-sm btn-primary" onclick="addParameter(event, null);">
\t\t\t\t\t\t\t\t\t<span><i class="fa-solid fa-plus"></i></span>
\t\t\t\t\t\t\t\t</button>
\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t<ul class="nav nav-tabs nav-tabs-sm flex-grow-1 min-w-0 mb-0 flex-nowrap overflow-auto" id="prs-method-param-tabs" role="tablist">
\t\t\t\t\t\t\t\t<li class="nav-item" role="presentation">
\t\t\t\t\t\t\t\t\t<button class="nav-link active" type="button" role="tab" id="prs-param-tab-trigger-0" data-bs-target="#span-parameter-0" data-bs-toggle="tab" aria-controls="span-parameter-0" aria-selected="true">#0</button>
\t\t\t\t\t\t\t\t</li>
\t\t\t\t\t\t\t</ul>
\t\t\t\t\t\t</div>
\t\t\t\t\t\t<div class="tab-content w-100" id="prs-method-param-tab-content">
\t\t\t\t\t\t\t<div class="tab-pane fade show active w-100 pb-2 prs-method-param-row" role="tabpanel" aria-labelledby="prs-param-tab-trigger-0" tabindex="0" prsIndex="0" id="span-parameter-0">"""

    if OLD_FORM_START not in h:
        raise SystemExit("OLD_FORM_START not found in html")
    h = h.replace(OLD_FORM_START, NEW_FORM_START, 1)

    _pre_end = h.find('pre-parameter-dg-test-0"></pre>')
    if _pre_end < 0:
        raise SystemExit("pre-parameter-dg-test-0 not found")
    _pre_end = h.find("</pre>", _pre_end) + len("</pre>")
    _stor = h.find(
        '\n\t\t\t</div>\n\n\t\t\t</div>\n\t\t\t\t<div class="tab-pane fade" id="prs-tab-pane-storage"',
        _pre_end,
    )
    if _stor < 0:
        raise SystemExit("end marker after parameters not found")
    OLD_CLOSE = h[_pre_end:_stor]
    if OLD_CLOSE.count("</div>") < 3:
        raise SystemExit("unexpected OLD_CLOSE structure")
    NEW_CLOSE = OLD_CLOSE + "\n\t\t\t\t\t\t</div>"
    h = h.replace(OLD_CLOSE, NEW_CLOSE, 1)

    h = h.replace(
        """<div class="smaller text-muted mb-2">Поиск по дереву: у результата кнопка <i class="fa-solid fa-anchor" aria-hidden="true"></i> <strong>добавляет</strong> тег в список (дубликаты не добавляются).</div>""",
        """<div class="smaller text-muted mb-2">Поиск по дереву: у результата кнопка <span class="prs-anchor-glyph" aria-hidden="true">&#x2693;</span> <strong>добавляет</strong> тег в список (дубликаты не добавляются).</div>""",
        1,
    )
    h = h.replace(
        """\t\t\t\t\t\t\t\t\t<div class="input-group input-group-sm">
\t\t\t\t\t\t\t\t\t\t<input type="search" class="form-control" id="input-parameter-tagSearch-0" placeholder="Имя, путь или id…" autocomplete="off"/>
\t\t\t\t\t\t\t\t\t\t<button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-0" title="Найти">Найти</button>
\t\t\t\t\t\t\t\t\t</div>""",
        """\t\t\t\t\t\t\t\t\t<div class="input-group input-group-sm mb-0">
\t\t\t\t\t\t\t\t\t\t<input type="search" class="form-control" id="input-parameter-tagSearch-0" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
\t\t\t\t\t\t\t\t\t\t<button type="button" class="btn btn-link prs-meth-search-trigger py-0 px-2 align-self-center" id="btn-parameter-tagSearch-0" title="Обновить поиск" aria-label="Найти">&#128269;</button>
\t\t\t\t\t\t\t\t\t</div>""",
        1,
    )

    # Compact index/name row
    h = h.replace(
        """<div class="w-100 d-flex flex-wrap align-items-end justify-content-between gap-2 mb-2 prs-method-param-head">
\t\t\t\t\t\t\t\t\t\t<div class="d-flex flex-wrap gap-2 flex-grow-1 min-w-0">
\t\t\t\t\t\t\t\t\t\t\t<div class="col-6 col-sm-auto" style="min-width:4.5rem">
\t\t\t\t\t\t\t\t\t\t\t\t<div class="text-muted smaller mb-0">Индекс</div>
\t\t\t\t\t\t\t\t\t\t\t\t<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-0"/>
\t\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t\t\t<div class="col-6 col-sm min-w-0 flex-grow-1" style="min-width:8rem">
\t\t\t\t\t\t\t\t\t\t\t\t<div class="text-muted smaller mb-0">Имя</div>
\t\t\t\t\t\t\t\t\t\t\t\t<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-0"/>
\t\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t\t</div>""",
        """<div class="w-100 d-flex flex-wrap align-items-end justify-content-between gap-2 mb-1 prs-method-param-head">
\t\t\t\t\t\t\t\t\t\t<div class="d-flex flex-wrap gap-2 flex-grow-1 min-w-0 align-items-end">
\t\t\t\t\t\t\t\t\t\t\t<div style="width:4.25rem;flex-shrink:0">
\t\t\t\t\t\t\t\t\t\t\t\t<div class="text-muted smaller mb-0">Индекс</div>
\t\t\t\t\t\t\t\t\t\t\t\t<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-0"/>
\t\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t\t\t<div class="min-w-0 flex-grow-1" style="min-width:6rem">
\t\t\t\t\t\t\t\t\t\t\t\t<div class="text-muted smaller mb-0">Имя</div>
\t\t\t\t\t\t\t\t\t\t\t\t<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-0"/>
\t\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t\t</div>""",
        1,
    )

    opts["html"] = h

    # --- onRender ---

    _ap = on.find("addParameter = (event, parameterData) =>")
    _dp = on.find("deleteParameter =", _ap)
    if _ap < 0 or _dp < 0:
        raise SystemExit("addParameter/deleteParameter markers not found")
    old_add = on[_ap:_dp]

    _a_if = on.find('      if (pane) pane.classList.add("show", "active");')
    _j_fl = on.find("function prsFilterInitiatorCatalogRows(kind, catalog, q) {", _a_if)
    if _a_if < 0 or _j_fl < 0:
        raise SystemExit("anchor for param tabs insert not found")
    _fl = "function prsFilterInitiatorCatalogRows(kind, catalog, q) {"
    anchor_tabs = on[_a_if : _j_fl + len(_fl)]

    insert_mid = """
function prsBindMethodParamTabsOnce() {
  const root = __prsConfiguratorHtmlNode;
  if (!root) return;
  const tabsRoot = root.getElementById("prs-method-param-tabs");
  const paneRoot = root.getElementById("prs-method-param-tab-content");
  if (!tabsRoot || !paneRoot) return;
  tabsRoot.querySelectorAll("button.nav-link").forEach(function (btn) {
    if (btn.dataset.prsMethParamTabBound === "1") return;
    btn.dataset.prsMethParamTabBound = "1";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var target = btn.getAttribute("data-bs-target");
      if (!target) return;
      tabsRoot.querySelectorAll(".nav-link").forEach(function (b) {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      paneRoot.querySelectorAll(".tab-pane").forEach(function (p) {
        p.classList.remove("show", "active");
      });
      var pane = root.querySelector(target);
      if (pane) pane.classList.add("show", "active");
    });
  });
}

function prsSyncMethodParamTabLabel(level) {
  var btn = __prsConfiguratorHtmlNode.getElementById("prs-param-tab-trigger-" + level);
  if (!btn) return;
  var ixEl = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsIndex-" + level);
  var nmEl = __prsConfiguratorHtmlNode.getElementById("input-parameter-cn-" + level);
  var ix = ixEl && ixEl.value != null ? String(ixEl.value).trim() : "";
  var nm = nmEl && nmEl.value != null ? String(nmEl.value).trim() : "";
  var t = "#" + (ix !== "" ? ix : String(level));
  if (nm) t += " · " + nm;
  else t += " · п." + level;
  btn.textContent = t;
}

function prsMethodParamActivateTab(level) {
  var root = __prsConfiguratorHtmlNode;
  if (!root) return;
  var tabsRoot = root.getElementById("prs-method-param-tabs");
  var paneRoot = root.getElementById("prs-method-param-tab-content");
  if (!tabsRoot || !paneRoot) return;
  var nb = root.getElementById("prs-param-tab-trigger-" + level);
  var np = root.getElementById("span-parameter-" + level);
  tabsRoot.querySelectorAll(".nav-link").forEach(function (x) {
    x.classList.remove("active");
    x.setAttribute("aria-selected", "false");
  });
  paneRoot.querySelectorAll(".tab-pane").forEach(function (x) {
    x.classList.remove("show", "active");
  });
  if (nb) {
    nb.classList.add("active");
    nb.setAttribute("aria-selected", "true");
  }
  if (np) {
    np.classList.add("show", "active");
  }
}

"""
    mark = "\n\nfunction prsFilterInitiatorCatalogRows"
    if mark not in anchor_tabs:
        raise SystemExit("unexpected anchor_tabs shape")
    _head, _tail = anchor_tabs.split(mark, 1)
    param_tabs_fns = _head + "\n\n" + insert_mid.strip() + "\n\nfunction prsFilterInitiatorCatalogRows" + _tail

    if "function prsBindMethodParamTabsOnce()" not in on:
        on = on.replace(anchor_tabs, param_tabs_fns, 1)

    on = on.replace(
        """    $("#div-list-parameters > div").each(function () {
      index = this.id.split("-").slice(-1);""",
        """    $("#prs-method-param-tab-content > .tab-pane").each(function () {
      index = this.id.split("-").slice(-1);""",
        1,
    )

    on = on.replace(
        """        $("#div-list-parameters").empty();
        (nodeData.parameters || []).map((item) => {
          addParameter(null, item);
        });""",
        """        var _pt = __prsConfiguratorHtmlNode.getElementById("prs-method-param-tabs");
        var _pc = __prsConfiguratorHtmlNode.getElementById("prs-method-param-tab-content");
        if (_pt) _pt.innerHTML = "";
        if (_pc) _pc.innerHTML = "";
        (nodeData.parameters || []).forEach((item) => {
          addParameter(null, item);
        });
        if (typeof prsBindMethodParamTabsOnce === "function") prsBindMethodParamTabsOnce();
        __prsConfiguratorHtmlNode.querySelectorAll(".prs-method-param-row[prsIndex]").forEach(function (el) {
          var lv = el.getAttribute("prsIndex");
          if (lv != null && typeof prsSyncMethodParamTabLabel === "function") prsSyncMethodParamTabLabel(Number(lv));
        });""",
        1,
    )

    new_add = r"""addParameter = (event, parameterData) => {
  getTagsPayload = {
    base: "prs",
    deref: false,
    scope: 2,
    filter: {
      objectClass: ["prsTag", "prsObject"]
    },
    attributes: ["cn", "objectClass"],
    getParent: true
  }
  params = new URLSearchParams({ q: JSON.stringify(getTagsPayload) }).toString();

  url = `${window.location.protocol}//${window.location.hostname}/v1/objects/?${params}`;
  fetch(url).then((response) => {
    if (!response.ok) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка получения списка тегов, тревог, расписаний.", false);
      return;
    }

    return response.json();
  }).then((data) => {
    if (!data) return;

    var tabsUl = __prsConfiguratorHtmlNode.getElementById("prs-method-param-tabs");
    var tabContent = __prsConfiguratorHtmlNode.getElementById("prs-method-param-tab-content");
    if (!tabsUl || !tabContent) return;

    var lastLevel = -1;
    tabContent.querySelectorAll(".prs-method-param-row[prsIndex]").forEach(function (el) {
      var n = Number(el.getAttribute("prsIndex"));
      if (isFinite(n) && n > lastLevel) lastLevel = n;
    });
    var newLevel = lastLevel + 1;

    var li = document.createElement("li");
    li.className = "nav-item";
    li.setAttribute("role", "presentation");
    var tabBtn = document.createElement("button");
    tabBtn.className = "nav-link";
    tabBtn.type = "button";
    tabBtn.setAttribute("role", "tab");
    tabBtn.id = "prs-param-tab-trigger-" + newLevel;
    tabBtn.setAttribute("data-bs-target", "#span-parameter-" + newLevel);
    tabBtn.setAttribute("data-bs-toggle", "tab");
    tabBtn.setAttribute("aria-controls", "span-parameter-" + newLevel);
    tabBtn.setAttribute("aria-selected", "false");
    tabBtn.textContent = "#" + newLevel;
    li.appendChild(tabBtn);
    tabsUl.appendChild(li);

    $("#prs-method-param-tab-content").append(`
      <div class="tab-pane fade w-100 pb-2 prs-method-param-row" role="tabpanel" aria-labelledby="prs-param-tab-trigger-${newLevel}" tabindex="0" prsIndex="${newLevel}" id="span-parameter-${newLevel}">
        <div class="w-100 d-flex flex-wrap align-items-end justify-content-between gap-2 mb-1 prs-method-param-head">
          <div class="d-flex flex-wrap gap-2 flex-grow-1 min-w-0 align-items-end">
            <div style="width:4.25rem;flex-shrink:0">
              <div class="text-muted smaller mb-0">Индекс</div>
              <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-${newLevel}"/>
            </div>
            <div class="min-w-0 flex-grow-1" style="min-width:6rem">
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
              <div class="smaller text-muted mb-2">Поиск → <span class="prs-anchor-glyph" aria-hidden="true">&#x2693;</span> <strong>добавляет</strong> тег (без дубликатов).</div>
              <input type="hidden" id="input-parameter-tagId-${newLevel}" value=""/>
              <div class="input-group input-group-sm mb-0">
                <input type="search" class="form-control" id="input-parameter-tagSearch-${newLevel}" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
                <button type="button" class="btn btn-link prs-meth-search-trigger py-0 px-2 align-self-center" id="btn-parameter-tagSearch-${newLevel}" title="Обновить поиск" aria-label="Найти">&#128269;</button>
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
    `);

    var level = newLevel;
    prsBindMethodParamTabsOnce();
    prsMethodParamActivateTab(level);
    prsPrepareParameterTagPicker(level, data.data, parameterData);
    if (!parameterData) prsMethodParamApplyJsonToBuilderFields(level, {});
    prsMethodParamUpdateUrlPreview(level);
    if (typeof prsSyncMethodParamTabLabel === "function") prsSyncMethodParamTabLabel(level);
  });
}
"""

    if old_add not in on:
        raise SystemExit("old addParameter block not found")
    on = on.replace(old_add, new_add, 1)

    old_del = """deleteParameter = (event) => {
  event.stopPropagation();
  var t = event.target;
  var row = t.closest && t.closest("[id^='span-parameter-']");
  if (row) row.remove();
  else {
    var targetEl = t;
    var deletedId = targetEl.id;
    if (deletedId.startsWith("i-"))
      targetEl.parentElement.parentElement.parentElement.remove();
    else
      targetEl.parentElement.remove();
  }
  if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
}"""

    new_del = """deleteParameter = (event) => {
  event.stopPropagation();
  var t = event.target;
  var row = t.closest && t.closest("[id^='span-parameter-']");
  if (!row) {
    var targetEl = t;
    var deletedId = targetEl.id;
    if (deletedId.startsWith("i-"))
      targetEl.parentElement.parentElement.parentElement.remove();
    else
      targetEl.parentElement.remove();
    if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
    return;
  }
  var level = row.getAttribute("prsIndex");
  var tabBtn = level != null ? __prsConfiguratorHtmlNode.getElementById("prs-param-tab-trigger-" + level) : null;
  if (tabBtn && tabBtn.closest("li")) tabBtn.closest("li").remove();
  row.remove();
  var paneRoot = __prsConfiguratorHtmlNode.getElementById("prs-method-param-tab-content");
  var firstPane = paneRoot && paneRoot.querySelector(".tab-pane");
  if (firstPane) {
    var lid = firstPane.id.replace("span-parameter-", "");
    if (lid && typeof prsMethodParamActivateTab === "function") prsMethodParamActivateTab(Number(lid));
  }
  if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
}"""

    if on.count(old_del) != 1:
        raise SystemExit("deleteParameter block count " + str(on.count(old_del)))
    on = on.replace(old_del, new_del, 1)

    old_paint = """function prsPaintParameterTagResults(level) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagResults-" + level);
  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  if (!box || !inp) return;
  const catalog = (window.prsParamPickerCatalog && window.prsParamPickerCatalog[level]) || [];
  const q = inp.value.trim().toLowerCase();
  box.classList.remove("d-none");
  box.innerHTML = "";
  if (!q) {
    box.innerHTML = '<div class="prs-method-search-hint text-muted smaller p-2">Введите запрос и нажмите «Найти».</div>';
    return;
  }
  const rows = catalog.filter((row) => {
    const cn = (row.cn || "").toLowerCase();
    const id = (row.id || "").toLowerCase();
    const path = (row.path || "").toLowerCase();
    return cn.includes(q) || id.includes(q) || path.includes(q);
  }).slice(0, 40);
  if (!rows.length) {
    box.innerHTML = '<div class="prs-method-search-hint text-muted smaller p-2">Нет совпадений</div>';
    return;
  }
  rows.forEach((row) => {
    const wrap = document.createElement("div");
    wrap.className = "prs-method-search-row";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "prs-anchor-btn";
    btn.title = "Добавить тег в запрос";
    btn.innerHTML = '<i class="fa-solid fa-anchor" aria-hidden="true"></i>';
    btn.addEventListener("click", function () {
      prsApplyParameterTagPick(level, row, false);
    });
    const main = document.createElement("div");
    main.className = "prs-method-search-main";
    main.innerHTML =
      '<div class="prs-method-search-path">' + prsEscapeHtml(row.path) + "</div>" +
      '<div class="prs-method-search-meta">' + prsEscapeHtml(row.id) + " · " + prsEscapeHtml(row.cn) + "</div>";
    wrap.appendChild(btn);
    wrap.appendChild(main);
    box.appendChild(wrap);
  });
}"""

    new_paint = """function prsPaintParameterTagResults(level) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagResults-" + level);
  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  if (!box || !inp) return;
  const catalog = (window.prsParamPickerCatalog && window.prsParamPickerCatalog[level]) || [];
  const q = inp.value.trim().toLowerCase();
  box.classList.remove("d-none");
  box.innerHTML = "";
  if (!q) {
    return;
  }
  const rows = catalog.filter((row) => {
    const cn = (row.cn || "").toLowerCase();
    const id = (row.id || "").toLowerCase();
    const path = (row.path || "").toLowerCase();
    return cn.includes(q) || id.includes(q) || path.includes(q);
  }).slice(0, 40);
  if (!rows.length) {
    box.innerHTML = '<div class="prs-method-search-hint text-muted smaller p-2">Нет совпадений</div>';
    return;
  }
  var chipBox = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagChips-" + level);
  var picked = [];
  if (chipBox) {
    chipBox.querySelectorAll("[data-prs-tag-id]").forEach(function (el) {
      picked.push(String(el.getAttribute("data-prs-tag-id")));
    });
  }
  rows.forEach((row) => {
    const wrap = document.createElement("div");
    wrap.className = "prs-method-search-row";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "prs-anchor-btn";
    var rid = String(row.id);
    var already = picked.indexOf(rid) >= 0;
    btn.disabled = already;
    btn.title = already ? "Уже в запросе" : "Добавить тег в запрос";
    btn.innerHTML = '<span class="prs-anchor-glyph" aria-hidden="true">&#x2693;</span>';
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      prsApplyParameterTagPick(level, row, false);
    });
    const main = document.createElement("div");
    main.className = "prs-method-search-main";
    main.innerHTML =
      '<div class="prs-method-search-path">' + prsEscapeHtml(row.path) + "</div>" +
      '<div class="prs-method-search-meta">' + prsEscapeHtml(row.id) + " · " + prsEscapeHtml(row.cn) + "</div>";
    wrap.appendChild(btn);
    wrap.appendChild(main);
    box.appendChild(wrap);
  });
}"""

    if on.count(old_paint) != 1:
        raise SystemExit("prsPaintParameterTagResults count " + str(on.count(old_paint)))
    on = on.replace(old_paint, new_paint, 1)

    on_in = """  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    var lv = Number(paramIndex);
    if (isFinite(lv)) prsMethodParamOnBuilderChange(lv);
  }

  prsUpdateSaveResetButtons();"""
    on_out = """  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    var lv = Number(paramIndex);
    if (isFinite(lv)) prsMethodParamOnBuilderChange(lv);
  }

  if (elId.startsWith("input-parameter-prsIndex-") || elId.startsWith("input-parameter-cn-")) {
    let paramIndex = elId.split("-").slice(-1);
    var lv2 = Number(paramIndex);
    if (isFinite(lv2) && typeof prsSyncMethodParamTabLabel === "function") prsSyncMethodParamTabLabel(lv2);
  }

  prsUpdateSaveResetButtons();"""
    if on.count(on_in) != 1:
        raise SystemExit("onInputChange injection count " + str(on.count(on_in)))
    on = on.replace(on_in, on_out, 1)

    boot_inj = """      try { if (typeof prsBindFormTabs === "function") prsBindFormTabs(); } catch (_eTb) {}"""
    boot_new = """      try { if (typeof prsBindFormTabs === "function") prsBindFormTabs(); } catch (_eTb) {}
      try { if (typeof prsBindMethodParamTabsOnce === "function") prsBindMethodParamTabsOnce(); } catch (_ePm) {}"""
    if boot_inj not in on:
        raise SystemExit("boot inject not found")
    on = on.replace(boot_inj, boot_new, 1)

    um = """      try {
        if (htmlNode) {
          htmlNode.querySelectorAll(".prs-method-initiators-wrap button.nav-link").forEach(function (b) { delete b.dataset.prsMethTabBound; });
        }
      } catch (_x) {}"""
    um_new = """      try {
        if (htmlNode) {
          htmlNode.querySelectorAll(".prs-method-initiators-wrap button.nav-link").forEach(function (b) { delete b.dataset.prsMethTabBound; });
          htmlNode.querySelectorAll("#prs-method-param-tabs button.nav-link").forEach(function (b) { delete b.dataset.prsMethParamTabBound; });
        }
      } catch (_x) {}"""
    if um not in on:
        raise SystemExit("unmount block not found")
    on = on.replace(um, um_new, 1)

    prep_old = """    prsMethodParamUpdateUrlPreview(level);
  }
}

function prsApplyParameterTagPick(level, row, silentInit) {"""
    prep_new = """    prsMethodParamUpdateUrlPreview(level);
    if (typeof prsSyncMethodParamTabLabel === "function") prsSyncMethodParamTabLabel(level);
  }
}

function prsApplyParameterTagPick(level, row, silentInit) {"""
    if prep_old not in on:
        raise SystemExit("prep_tail anchor not found")
    on = on.replace(prep_old, prep_new, 1)

    css_add = """
/* Закладки параметров метода */
.prs-method-params-wrap .nav-tabs-sm .nav-link { padding: 0.35rem 0.55rem; font-size: 0.8125rem; white-space: nowrap; }
.prs-method-param-toolbar { min-width: 0; }
.prs-method-param-dg-host { min-width: 0; }
"""
    if "prs-method-params-wrap .nav-tabs-sm" not in css:
        opts["css"] = css + css_add

    opts["onRender"] = on
    out = json.dumps(d, ensure_ascii=False, indent=2)
    json.loads(out)
    P.write_text(out + "\n", encoding="utf-8")
    print("OK", P)


if __name__ == "__main__":
    main()
