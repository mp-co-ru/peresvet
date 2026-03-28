#!/usr/bin/env python3
"""Патч Configurator.json: метод — вкладки Теги/Расписания, поиск с якорем, параметры — один тег через якорь."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "src/configurator_grafana/Configurator.json"

OLD_HTML_BLOCK = r'''<div class="input-group mt-2" id="div-initiatedBy">
				<span class="input-group-text prs-input-label space-between">Инициаторы:
							<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip"
								title="Список того, что инициирует запуск метода. Теги: изменение значения указанного тега; тревоги: возникновение тревоги; расписание: запланированный момент времени. Все эти события инициируют запуск метода.">
							</i>
						</span>
				<div class="form-control d-flex">
					<div class="nav flex-column nav-pills m-2" id="v-pills-tab" role="tablist" aria-orientation="vertical">
						<button class="nav-link nav-link-icon active text-start" id="v-pills-Tags-tab" data-bs-toggle="pill" data-bs-target="#v-pills-Tags" type="button" role="tab" aria-controls="v-pills-Tags" aria-selected="true" onClick="initiatorsTabClicked('tags')">
									<i class="fa-solid fa-tags"></i>&nbsp;&nbsp;Теги
								</button>
						<!--
								<button class="nav-link nav-link-icon text-start" id="v-pills-Alerts-tab" data-bs-toggle="pill" data-bs-target="#v-pills-Alerts" type="button" role="tab" aria-controls="v-pills-Alerts" aria-selected="false">
									<i class="fa-solid fa-bell"></i>&nbsp;&nbsp;Тревоги
								</button>
								-->
						<button class="nav-link nav-link-icon text-start" id="v-pills-Schedules-tab" data-bs-toggle="pill" data-bs-target="#v-pills-Schedules" type="button" role="tab" aria-controls="v-pills-Schedules" aria-selected="false" onClick="initiatorsTabClicked('schedules')">
									<i class="fa-solid fa-clock"></i>&nbsp;&nbsp;Расписания
								</button>
					</div>
					<div class="tab-content" id="v-pills-tabContent">
						<div class="tab-pane fade show active" id="v-pills-Tags" role="tabpanel" aria-labelledby="v-pills-Tags-tab"
							tabindex="0">
							<input type="search" class="form-control form-control-sm mt-1" id="input-initiatorSearchTags" placeholder="Поиск тега по имени или id…" autocomplete="off"/>
							<div class="prs-picker-list mt-1" id="div-initiatorListTags"></div>
							<div class="text-muted smaller mt-1 mb-0">Выбранные теги:</div>
							<div class="prs-chips mt-1" id="div-initiatorChipsTags"></div>
							<select class="d-none" id="input-initiatedByTags" multiple></select>
						</div>
						<!--
								<div class="tab-pane fade" id="v-pills-Alerts" role="tabpanel" aria-labelledby="v-pills-Alerts-tab" tabindex="0">
									<select prsAttribute="initiatedBy" onchange="onInputChange(event);" id="input-initiatedByAlerts" class="form-select mt-1" size="5" multiple>
										<option selected value="true">Текст текст текст</option>
										<option value="false">Текст текст текст</option>
									</select>
								</div>
								-->
						<div class="tab-pane fade" id="v-pills-Schedules" role="tabpanel" aria-labelledby="v-pills-Schedules-tab"
							tabindex="0">
							<input type="search" class="form-control form-control-sm mt-1" id="input-initiatorSearchSchedules" placeholder="Поиск расписания по имени или id…" autocomplete="off"/>
							<div class="prs-picker-list mt-1" id="div-initiatorListSchedules"></div>
							<div class="text-muted smaller mt-1 mb-0">Выбранные расписания:</div>
							<div class="prs-chips mt-1" id="div-initiatorChipsSchedules"></div>
							<select class="d-none" id="input-initiatedBySchedules" multiple></select>
						</div>
					</div>
				</div>
			</div>'''

NEW_HTML_BLOCK = r'''<div class="input-group mt-2" id="div-initiatedBy">
				<span class="input-group-text prs-input-label space-between">Инициаторы:
							<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip"
								title="Список того, что инициирует запуск метода. Теги: изменение значения указанного тега; расписание: запланированный момент времени. Добавляйте через поиск и кнопку с якорем.">
							</i>
						</span>
				<div class="form-control p-2 prs-method-initiators-wrap">
					<ul class="nav nav-tabs nav-tabs-sm mb-2 flex-nowrap flex-shrink-0" id="prs-method-init-tabs" role="tablist">
						<li class="nav-item" role="presentation">
							<button class="nav-link active" id="prs-meth-tab-tags" type="button" role="tab" data-bs-toggle="tab" data-bs-target="#prs-meth-pane-tags" aria-controls="prs-meth-pane-tags" aria-selected="true">Теги</button>
						</li>
						<li class="nav-item" role="presentation">
							<button class="nav-link" id="prs-meth-tab-schedules" type="button" role="tab" data-bs-toggle="tab" data-bs-target="#prs-meth-pane-schedules" aria-controls="prs-meth-pane-schedules" aria-selected="false">Расписания</button>
						</li>
					</ul>
					<div class="tab-content" id="prs-method-init-tab-content">
						<div class="tab-pane fade show active" id="prs-meth-pane-tags" role="tabpanel" aria-labelledby="prs-meth-tab-tags" tabindex="0">
							<div class="input-group input-group-sm mb-2">
								<input type="search" class="form-control" id="input-initiatorSearchTags" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
								<button type="button" class="btn btn-outline-secondary" id="btn-initiatorSearchTags" title="Найти"><i class="fa-solid fa-magnifying-glass"></i></button>
							</div>
							<div class="prs-method-search-results" id="div-initiatorResultsTags"></div>
							<div class="text-muted smaller mt-2 mb-0">Выбранные теги:</div>
							<div class="prs-chips mt-1" id="div-initiatorChipsTags"></div>
							<select class="d-none" id="input-initiatedByTags" multiple></select>
						</div>
						<div class="tab-pane fade" id="prs-meth-pane-schedules" role="tabpanel" aria-labelledby="prs-meth-tab-schedules" tabindex="0">
							<div class="input-group input-group-sm mb-2">
								<input type="search" class="form-control" id="input-initiatorSearchSchedules" placeholder="Поиск расписания по имени, пути или id…" autocomplete="off"/>
								<button type="button" class="btn btn-outline-secondary" id="btn-initiatorSearchSchedules" title="Найти"><i class="fa-solid fa-magnifying-glass"></i></button>
							</div>
							<div class="prs-method-search-results" id="div-initiatorResultsSchedules"></div>
							<div class="text-muted smaller mt-2 mb-0">Выбранные расписания:</div>
							<div class="prs-chips mt-1" id="div-initiatorChipsSchedules"></div>
							<select class="d-none" id="input-initiatedBySchedules" multiple></select>
						</div>
					</div>
				</div>
			</div>'''

OLD_JS_BLOCK = """function prsRenderInitiatorPickers() {
  prsRenderOneInitiatorKind("Tags", window.prsInitiatorCatalogTags || []);
  prsRenderOneInitiatorKind("Schedules", window.prsInitiatorCatalogSchedules || []);
  prsUpdateInitiatorFilter("Tags");
  prsUpdateInitiatorFilter("Schedules");
}

function prsRenderOneInitiatorKind(kind, catalog) {
  const listEl = __prsConfiguratorHtmlNode.getElementById("div-initiatorList" + kind);
  if (!listEl) return;
  listEl.innerHTML = "";
  catalog.forEach((row) => {
    const sel = prsMethodInitiatorIds.includes(row.id);
    const div = document.createElement("div");
    div.className = "prs-picker-row";
    div.dataset.id = row.id;
    div.dataset.cn = (row.cn || "").toLowerCase();
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "form-check-input me-1";
    cb.disabled = !!row.disabled;
    cb.checked = sel;
    cb.addEventListener("change", function () {
      if (cb.checked) {
        if (!prsMethodInitiatorIds.includes(row.id)) prsMethodInitiatorIds.push(row.id);
      } else {
        prsMethodInitiatorIds = prsMethodInitiatorIds.filter((x) => x !== row.id);
      }
      prsRenderInitiatorChips(kind);
      prsMarkInitiatorsDirty();
    });
    const lab = document.createElement("span");
    lab.textContent = row.cn + "  (" + row.id + ")";
    div.appendChild(cb);
    div.appendChild(lab);
    listEl.appendChild(div);
  });
  prsRenderInitiatorChips(kind);
}

function prsRenderInitiatorChips(kind) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-initiatorChips" + kind);
  if (!box) return;
  const cat = kind === "Tags" ? (window.prsInitiatorCatalogTags || []) : (window.prsInitiatorCatalogSchedules || []);
  box.innerHTML = "";
  prsMethodInitiatorIds.forEach((id) => {
    const row = cat.find((r) => r.id === id);
    if (!row) return;
    const chip = document.createElement("span");
    chip.className = "prs-chip";
    chip.innerHTML = '<span class="text-truncate" style="max-width:14rem">' + (row.cn || id) + "</span>" +
      '<button type="button" aria-label="Убрать">&times;</button>';
    chip.querySelector("button").addEventListener("click", function () {
      prsMethodInitiatorIds = prsMethodInitiatorIds.filter((x) => x !== id);
      prsRenderInitiatorPickers();
      prsMarkInitiatorsDirty();
    });
    box.appendChild(chip);
  });
}

function prsUpdateInitiatorFilter(kind) {
  const inp = __prsConfiguratorHtmlNode.getElementById("input-initiatorSearch" + kind);
  const q = (inp && inp.value) ? inp.value.trim().toLowerCase() : "";
  const listEl = __prsConfiguratorHtmlNode.getElementById("div-initiatorList" + kind);
  if (!listEl) return;
  [...listEl.children].forEach((row) => {
    const cn = row.dataset.cn || "";
    const id = (row.dataset.id || "").toLowerCase();
    row.classList.toggle("prs-hidden", q && !cn.includes(q) && !id.includes(q));
  });
}

function prsBindInitiatorSearch() {
  ["Tags", "Schedules"].forEach((kind) => {
    const inp = __prsConfiguratorHtmlNode.getElementById("input-initiatorSearch" + kind);
    if (inp && !inp.dataset.prsBound) {
      inp.dataset.prsBound = "1";
      inp.addEventListener("input", function () { prsUpdateInitiatorFilter(kind); });
    }
  });
}

"""

NEW_JS_BLOCK = r"""function prsEscapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

var prsInitiatorSearchTimers = { Tags: 0, Schedules: 0 };

function prsBuildPathMapFromNodes(allNodes) {
  const byId = {};
  (allNodes.data || []).forEach((dataItem) => {
    byId[dataItem.id] = {
      id: dataItem.id,
      cn: (dataItem.attributes.cn && dataItem.attributes.cn[0]) || "",
      oc: (dataItem.attributes.objectClass && dataItem.attributes.objectClass[0]) || "",
      parentId: dataItem.parentId || null
    };
  });
  const rootIds = new Set(["tags", "schedules", "objects", "connectors", "alerts", "methods", "dataStorages"]);
  function pathFor(id) {
    const parts = [];
    let cur = id;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      seen.add(cur);
      const n = byId[cur];
      if (!n) break;
      if (rootIds.has(cur)) break;
      parts.unshift(n.cn || cur);
      cur = n.parentId;
    }
    return parts.length ? parts.join(" / ") : ((byId[id] && byId[id].cn) || id);
  }
  return { byId, pathFor };
}

function prsBindMethodInitiatorTabsOnce() {
  const root = __prsConfiguratorHtmlNode;
  if (!root || root.dataset.prsMethodInitTabsBound === "1") return;
  const wrap = root.querySelector(".prs-method-initiators-wrap");
  if (!wrap) return;
  root.dataset.prsMethodInitTabsBound = "1";
  wrap.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var target = btn.getAttribute("data-bs-target");
      if (!target) return;
      wrap.querySelectorAll(".nav-link").forEach(function (b) {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      wrap.querySelectorAll(".tab-pane").forEach(function (p) {
        p.classList.remove("show", "active");
      });
      var pane = root.querySelector(target);
      if (pane) pane.classList.add("show", "active");
    });
  });
}

function prsFilterInitiatorCatalogRows(kind, catalog, q) {
  q = (q || "").trim().toLowerCase();
  if (!q) return [];
  return catalog.filter((row) => {
    if (row.disabled) return false;
    const cn = (row.cn || "").toLowerCase();
    const id = (row.id || "").toLowerCase();
    const path = (row.path || "").toLowerCase();
    return cn.includes(q) || id.includes(q) || path.includes(q);
  }).slice(0, 50);
}

function prsPaintInitiatorResults(kind) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-initiatorResults" + kind);
  if (!box) return;
  const inp = __prsConfiguratorHtmlNode.getElementById("input-initiatorSearch" + kind);
  const q = inp ? inp.value : "";
  const catalog = kind === "Tags" ? (window.prsInitiatorCatalogTags || []) : (window.prsInitiatorCatalogSchedules || []);
  const rows = prsFilterInitiatorCatalogRows(kind, catalog, q);
  box.innerHTML = "";
  if (!String(q).trim()) {
    box.innerHTML = '<div class="prs-method-search-hint text-muted smaller p-2">Введите часть имени, пути или id и нажмите «Найти» или продолжайте ввод.</div>';
    return;
  }
  if (!rows.length) {
    box.innerHTML = '<div class="prs-method-search-hint text-muted smaller p-2">Нет совпадений</div>';
    return;
  }
  rows.forEach((row) => {
    const already = prsMethodInitiatorIds.includes(row.id);
    const wrap = document.createElement("div");
    wrap.className = "prs-method-search-row";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "prs-anchor-btn";
    btn.title = already ? "Уже в списке" : "Добавить к инициаторам";
    btn.disabled = !!row.disabled || already;
    btn.innerHTML = '<i class="fa-solid fa-anchor" aria-hidden="true"></i>';
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      if (!prsMethodInitiatorIds.includes(row.id)) prsMethodInitiatorIds.push(row.id);
      prsRenderInitiatorChips(kind);
      prsPaintInitiatorResults(kind);
      prsMarkInitiatorsDirty();
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
}

function prsRenderInitiatorPickers() {
  prsBindMethodInitiatorTabsOnce();
  prsRenderInitiatorChips("Tags");
  prsRenderInitiatorChips("Schedules");
  prsPaintInitiatorResults("Tags");
  prsPaintInitiatorResults("Schedules");
}

function prsRenderInitiatorChips(kind) {
  const box = __prsConfiguratorHtmlNode.getElementById("div-initiatorChips" + kind);
  if (!box) return;
  const cat = kind === "Tags" ? (window.prsInitiatorCatalogTags || []) : (window.prsInitiatorCatalogSchedules || []);
  box.innerHTML = "";
  prsMethodInitiatorIds.forEach((id) => {
    const row = cat.find((r) => r.id === id);
    if (!row) return;
    const chip = document.createElement("span");
    chip.className = "prs-chip";
    chip.innerHTML = '<span class="text-truncate" style="max-width:14rem">' + prsEscapeHtml(row.cn || id) + "</span>" +
      '<button type="button" aria-label="Убрать">&times;</button>';
    chip.querySelector("button").addEventListener("click", function () {
      prsMethodInitiatorIds = prsMethodInitiatorIds.filter((x) => x !== id);
      prsRenderInitiatorPickers();
      prsMarkInitiatorsDirty();
    });
    box.appendChild(chip);
  });
}

function prsBindInitiatorSearch() {
  ["Tags", "Schedules"].forEach((kind) => {
    const inp = __prsConfiguratorHtmlNode.getElementById("input-initiatorSearch" + kind);
    if (inp && !inp.dataset.prsBound) {
      inp.dataset.prsBound = "1";
      inp.addEventListener("input", function () {
        clearTimeout(prsInitiatorSearchTimers[kind]);
        prsInitiatorSearchTimers[kind] = setTimeout(function () {
          prsPaintInitiatorResults(kind);
        }, 280);
      });
    }
    const btn = __prsConfiguratorHtmlNode.getElementById("btn-initiatorSearch" + kind);
    if (btn && !btn.dataset.prsBound) {
      btn.dataset.prsBound = "1";
      btn.addEventListener("click", function () {
        prsPaintInitiatorResults(kind);
      });
    }
  });
}


"""

OLD_FILL = """function prsFillMethodInitiators(nodeData, allNodes) {
  prsMethodParentId = nodeData.parentId || "";
  prsMethodInitiatorIds = (nodeData.initiatedBy || []).slice();
  prsMethodInitiatorInit = JSON.stringify([...prsMethodInitiatorIds].sort());
  window.prsInitiatorCatalogTags = [];
  window.prsInitiatorCatalogSchedules = [];
  (allNodes.data || []).forEach((dataItem) => {
    const oc = dataItem.attributes.objectClass[0];
    const row = { id: dataItem.id, cn: dataItem.attributes.cn[0], disabled: dataItem.id === prsMethodParentId };
    if (oc === "prsTag") window.prsInitiatorCatalogTags.push(row);
    else if (oc === "prsSchedule") window.prsInitiatorCatalogSchedules.push(row);
  });
  prsRenderInitiatorPickers();
  prsBindInitiatorSearch();
}"""

NEW_FILL = """function prsFillMethodInitiators(nodeData, allNodes) {
  prsMethodParentId = nodeData.parentId || "";
  prsMethodInitiatorIds = (nodeData.initiatedBy || []).slice();
  prsMethodInitiatorInit = JSON.stringify([...prsMethodInitiatorIds].sort());
  const { pathFor } = prsBuildPathMapFromNodes(allNodes);
  window.prsInitiatorCatalogTags = [];
  window.prsInitiatorCatalogSchedules = [];
  (allNodes.data || []).forEach((dataItem) => {
    const oc = dataItem.attributes.objectClass[0];
    const row = {
      id: dataItem.id,
      cn: dataItem.attributes.cn[0],
      path: pathFor(dataItem.id),
      disabled: dataItem.id === prsMethodParentId
    };
    if (oc === "prsTag") window.prsInitiatorCatalogTags.push(row);
    else if (oc === "prsSchedule") window.prsInitiatorCatalogSchedules.push(row);
  });
  prsRenderInitiatorPickers();
  prsBindInitiatorSearch();
}"""

OLD_GETPAYLOAD = """        attributes: ["cn", "objectClass"]
      }
      let params = new URLSearchParams({ q: JSON.stringify(getTagsAlertsSchedulesPayload) }).toString();

      let url = `${window.location.protocol}//${window.location.hostname}/v1/objects/?${params}`;
      fetch(url).then((response) => {
        if (!response.ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка получения списка тегов, тревог, расписаний.", false);
          return;
        }
        return response.json();
      }).then((allNodes) => {
        if (!allNodes) return;
        prsFillMethodInitiators(nodeData, allNodes);"""

NEW_GETPAYLOAD = """        attributes: ["cn", "objectClass"],
        getParent: true
      }
      let params = new URLSearchParams({ q: JSON.stringify(getTagsAlertsSchedulesPayload) }).toString();

      let url = `${window.location.protocol}//${window.location.hostname}/v1/objects/?${params}`;
      fetch(url).then((response) => {
        if (!response.ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка получения списка тегов, тревог, расписаний.", false);
          return;
        }
        return response.json();
      }).then((allNodes) => {
        if (!allNodes) return;
        prsFillMethodInitiators(nodeData, allNodes);"""

OLD_ADDPARAM_SNIP = r"""  getTagsPayload = {
    base: "prs",
    deref: false,
    scope: 2,
    filter: {
      objectClass: ["prsTag"]
    },
    attributes: ["cn", "objectClass"]
  }
  params = new URLSearchParams({ q: JSON.stringify(getTagsPayload) }).toString();"""

NEW_ADDPARAM_SNIP = r"""  getTagsPayload = {
    base: "prs",
    deref: false,
    scope: 2,
    filter: {
      objectClass: ["prsTag"]
    },
    attributes: ["cn", "objectClass"],
    getParent: true
  }
  params = new URLSearchParams({ q: JSON.stringify(getTagsPayload) }).toString();"""

OLD_APPEND = r"""        <div class="col-4 me-2">
          <input type="search" class="form-control form-control-sm mb-1" placeholder="Поиск тега…" oninput="prsFilterParamTagSelect(${newLevel}, this.value)"/>
          <select prsAttribute="parameter" onchange="onInputChange(event);" id="input-parameter-tagId-${newLevel}" class="form-select form-select-sm" size="1">
            <option selected value="ttt">&#62;=</option>
            <option value="ttttt">&#60;</option>
          </select>
        </div>"""

NEW_APPEND = r"""        <div class="col-4 me-2 prs-param-tag-wrap">
          <input type="hidden" id="input-parameter-tagId-${newLevel}" value=""/>
          <div class="input-group input-group-sm">
            <input type="search" class="form-control" id="input-parameter-tagSearch-${newLevel}" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
            <button type="button" class="btn btn-outline-secondary" id="btn-parameter-tagSearch-${newLevel}" title="Найти"><i class="fa-solid fa-magnifying-glass"></i></button>
          </div>
          <div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-${newLevel}"></div>
          <div class="small text-muted mt-1 text-truncate" id="span-parameter-tagPick-${newLevel}">не выбран</div>
        </div>"""

OLD_AFTER_APPEND = r"""    allTags = data.data;
    level = newLevel;
    tags = [];
    parameter_tags_select = $(`#input-parameter-tagId-${level}`);
    $(`#input-parameter-tagId-${level} option`).remove();
    allTags.map((dataItem) => {
      tags.push({
        cn: dataItem.attributes.cn[0],
        id: dataItem.id
      });
    });
    tags.map((el) => {
      parameter_tags_select.append(`<option value="${el.id}">${el.cn}&nbsp;(${el.id})</option>`);
    });
    parameter_tags_select.val("");
    if (parameterData) {
      let index = Number(parameterData.attributes.prsIndex[0]);
      let name = parameterData.attributes.cn[0];
      let config_text = parameterData.attributes.prsJsonConfigString[0];

      let config = JSON.parse(config_text);
      if (Array.isArray(config.tagId))
        tagId = config.tagId[0];
      else
        tagId = config.tagId;

      parameter_tags_select.val(tagId);

      $(`#input-parameter-prsIndex-${level}`).val(index);
      $(`#input-parameter-cn-${level}`).val(name);
      $(`#input-parameter-prsJsonConfigString-${level}`).val(config_text);
    }
  });
}"""

NEW_AFTER_APPEND = r"""    level = newLevel;
    prsPrepareParameterTagPicker(level, data.data, parameterData);
  });
}"""

OLD_FILTER_FN = """function prsFilterParamTagSelect(level, q) {
  q = (q || "").trim().toLowerCase();
  const sel = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  if (!sel) return;
  [...sel.options].forEach((opt) => {
    const t = (opt.textContent || "").toLowerCase();
    opt.hidden = !!(q && !t.includes(q));
  });
}



"""

NEW_FILTER_FN = r"""var prsParamSearchTimers = {};

function prsPrepareParameterTagPicker(level, allTagsData, parameterData) {
  const { pathFor } = prsBuildPathMapFromNodes({ data: allTagsData });
  const rows = (allTagsData || []).map((dataItem) => ({
    id: dataItem.id,
    cn: dataItem.attributes.cn[0],
    path: pathFor(dataItem.id)
  }));
  if (!window.prsParamPickerCatalog) window.prsParamPickerCatalog = {};
  window.prsParamPickerCatalog[level] = rows;

  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  const btn = __prsConfiguratorHtmlNode.getElementById("btn-parameter-tagSearch-" + level);
  if (inp && !inp.dataset.prsBound) {
    inp.dataset.prsBound = "1";
    inp.addEventListener("input", function () {
      clearTimeout(prsParamSearchTimers[level]);
      prsParamSearchTimers[level] = setTimeout(function () {
        prsPaintParameterTagResults(level);
      }, 280);
    });
  }
  if (btn && !btn.dataset.prsBound) {
    btn.dataset.prsBound = "1";
    btn.addEventListener("click", function () {
      prsPaintParameterTagResults(level);
    });
  }

  if (parameterData) {
    let index = Number(parameterData.attributes.prsIndex[0]);
    let name = parameterData.attributes.cn[0];
    let config_text = parameterData.attributes.prsJsonConfigString[0];
    let config = JSON.parse(config_text);
    let tagId;
    if (Array.isArray(config.tagId)) tagId = config.tagId[0];
    else tagId = config.tagId;
    $(`#input-parameter-prsIndex-${level}`).val(index).attr("init-value", String(index));
    $(`#input-parameter-cn-${level}`).val(name).attr("init-value", name);
    $(`#input-parameter-prsJsonConfigString-${level}`).val(config_text).attr("init-value", config_text);
    const row = rows.find((r) => r.id === tagId);
    if (row) prsApplyParameterTagPick(level, row, true);
    else if (tagId) {
      const hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
      const span = __prsConfiguratorHtmlNode.getElementById("span-parameter-tagPick-" + level);
      if (hid) { hid.value = tagId; hid.setAttribute("init-value", tagId); }
      if (span) span.textContent = tagId;
    }
  }
}

function prsApplyParameterTagPick(level, row, silentInit) {
  const hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  const span = __prsConfiguratorHtmlNode.getElementById("span-parameter-tagPick-" + level);
  const res = __prsConfiguratorHtmlNode.getElementById("div-parameter-tagResults-" + level);
  const inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagSearch-" + level);
  if (hid) hid.value = row.id;
  if (span) span.textContent = (row.cn || "") + " (" + row.id + ")";
  if (res) {
    res.classList.add("d-none");
    res.innerHTML = "";
  }
  if (inp) inp.value = "";
  const ta = __prsConfiguratorHtmlNode.querySelector("#input-parameter-prsJsonConfigString-" + level);
  if (ta) {
    const jsonStr = JSON.stringify({ tagId: [row.id] }, null, "\t");
    $(ta).val(jsonStr);
    if (silentInit) ta.setAttribute("init-value", jsonStr);
    else $(ta).addClass("value-changed");
  }
  if (!silentInit) {
    const inputs = __prsConfiguratorHtmlNode.querySelectorAll(".value-changed");
    if (inputs.length > 0) {
      $("#but-save").removeClass("disabled");
      $("#but-reset").removeClass("disabled");
    }
  }
}

function prsPaintParameterTagResults(level) {
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
    btn.title = "Выбрать этот тег";
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
}



"""

CSS_SNIPPET = """
/* Поиск тегов/расписаний (метод) — как в prs-inkscape-grafana */
.prs-method-search-results {
  max-height: 14rem;
  overflow-y: auto;
  border: 1px solid var(--prs-border, #dee2e6);
  border-radius: var(--prs-radius, 0.375rem);
  background: var(--prs-bg, #fff);
}
.prs-method-search-row {
  display: flex;
  align-items: stretch;
  gap: 0.35rem;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--prs-border, #dee2e6);
}
.prs-method-search-row:last-child { border-bottom: none; }
.prs-method-search-row:hover { background: var(--ioterra-teal-light, #e6f2f4); }
.prs-anchor-btn {
  flex: 0 0 auto;
  align-self: flex-start;
  border: none;
  background: transparent;
  color: var(--prs-primary, #2c707f);
  padding: 0.2rem 0.4rem;
  border-radius: 0.25rem;
}
.prs-anchor-btn:hover:not(:disabled) { background: rgba(44, 112, 127, 0.12); }
.prs-anchor-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.prs-method-search-main { flex: 1; min-width: 0; }
.prs-method-search-path { font-size: 0.8125rem; font-weight: 600; line-height: 1.25; }
.prs-method-search-meta { font-size: 0.7rem; color: var(--prs-muted, #5c6569); font-family: ui-monospace, monospace; margin-top: 0.15rem; word-break: break-all; }
.prs-method-initiators-wrap .nav-tabs .nav-link { padding: 0.35rem 0.65rem; font-size: 0.8125rem; }
.prs-param-tag-wrap { min-width: 0; }
"""


def main() -> None:
    data = json.loads(CFG.read_text(encoding="utf-8"))
    html = data["panels"][0]["options"]["html"]
    if OLD_HTML_BLOCK not in html:
        raise SystemExit("OLD_HTML_BLOCK not found in html — уже патчили или разметка изменилась")
    html = html.replace(OLD_HTML_BLOCK, NEW_HTML_BLOCK, 1)
    data["panels"][0]["options"]["html"] = html

    css = data["panels"][0]["options"]["css"]
    if ".prs-method-search-results" not in css:
        data["panels"][0]["options"]["css"] = css.rstrip() + "\n" + CSS_SNIPPET

    js = data["panels"][0]["options"]["onRender"]
    n = 0
    if OLD_JS_BLOCK in js:
        js = js.replace(OLD_JS_BLOCK, NEW_JS_BLOCK, 1)
        n += 1
    else:
        raise SystemExit("OLD_JS_BLOCK not found in onRender")

    if OLD_FILL not in js:
        raise SystemExit("OLD_FILL not found")
    js = js.replace(OLD_FILL, NEW_FILL, 1)

    if OLD_GETPAYLOAD not in js:
        raise SystemExit("OLD_GETPAYLOAD not found")
    js = js.replace(OLD_GETPAYLOAD, NEW_GETPAYLOAD, 1)

    if OLD_ADDPARAM_SNIP not in js:
        raise SystemExit("OLD_ADDPARAM_SNIP not found")
    js = js.replace(OLD_ADDPARAM_SNIP, NEW_ADDPARAM_SNIP, 1)

    if OLD_APPEND not in js:
        raise SystemExit("OLD_APPEND not found")
    js = js.replace(OLD_APPEND, NEW_APPEND, 1)

    if OLD_AFTER_APPEND not in js:
        raise SystemExit("OLD_AFTER_APPEND not found")
    js = js.replace(OLD_AFTER_APPEND, NEW_AFTER_APPEND, 1)

    if OLD_FILTER_FN not in js:
        raise SystemExit("OLD_FILTER_FN not found")
    js = js.replace(OLD_FILTER_FN, NEW_FILTER_FN, 1)

    # onInputChange: убрать ветку select parameter-tagId (теперь hidden + якорь)
    old_on = """  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    selectedTag = $(targetEl).val();
    payload = {
      tagId: [selectedTag]
    }
    $(`#input-parameter-prsJsonConfigString-${paramIndex}`).val(
      JSON.stringify(payload, null, "\t")
    ).addClass("value-changed");
  }
"""
    if old_on in js:
        js = js.replace(old_on, "", 1)

    data["panels"][0]["options"]["onRender"] = js

    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK:", CFG, "replacements ok")


if __name__ == "__main__":
    main()
