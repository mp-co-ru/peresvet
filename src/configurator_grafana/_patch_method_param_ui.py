#!/usr/bin/env python3
"""One-off patch: method parameter DataGet builder UI in Configurator.json"""
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "Configurator.json"

OLD_ROW = r'''<div class="d-flex align-items-center" prsIndex="0" id="span-parameter-0">
								<div class="col-1 me-2">
									<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-0"/>
								</div>
								<div class="col-1 me-2">
									<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-0"/>
								</div>
								<div class="col-4 me-2 prs-param-tag-wrap">
									<input type="hidden" id="input-parameter-tagId-0" value=""/>
									<div class="input-group input-group-sm">
										<input type="search" class="form-control" id="input-parameter-tagSearch-0" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
										<button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-0" title="Найти">Найти</button>
									</div>
									<div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-0"></div>
									<div class="prs-param-tag-pick-label small text-muted mt-1" id="span-parameter-tagPick-0">не выбран</div>
								</div>
								<div class="col me-2">
									<!--
										<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-prsJsonConfigString-0"/>
										-->
									<textarea class="form-control form-control-sm" prsAttribute="parameter" autocomplete="off" id="input-parameter-prsJsonConfigString-0">{"data": []}</textarea>
								</div>
								<button id="but-deleteParameter-0" class="btn btn-sm m-1 btn-danger" onclick="deleteParameter(event);">
										<span><i class="fa-solid fa-minus" id="i-deleteParameter-0"></i></span>
									</button>
							</div>'''

NEW_ROW_0 = r'''<div class="d-flex flex-wrap align-items-start w-100 border-bottom pb-2 mb-2 prs-method-param-row" prsIndex="0" id="span-parameter-0">
								<div class="col-6 col-md-1 me-2 mb-1">
									<div class="text-muted smaller mb-0">Индекс</div>
									<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-0"/>
								</div>
								<div class="col-6 col-md-1 me-2 mb-1">
									<div class="text-muted smaller mb-0">Имя</div>
									<input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-0"/>
								</div>
								<div class="col-12 col-md-3 me-2 prs-param-tag-wrap mb-1">
									<div class="text-muted smaller mb-0">Тег (источник)</div>
									<input type="hidden" id="input-parameter-tagId-0" value=""/>
									<div class="input-group input-group-sm">
										<input type="search" class="form-control" id="input-parameter-tagSearch-0" placeholder="Поиск тега…" autocomplete="off"/>
										<button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-0" title="Найти">Найти</button>
									</div>
									<div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-0"></div>
									<div class="prs-param-tag-pick-label small text-muted mt-1" id="span-parameter-tagPick-0">не выбран</div>
								</div>
								<div class="col-12 col-md min-w-0 mb-1 prs-method-param-dg-host">
									<div class="prs-method-param-dg border rounded p-2 bg-light">
										<div class="smaller text-muted mb-2">Тело запроса <code>GET /v1/data/</code> (как DataGet). При запуске метода платформа подставляет <strong>finish</strong> из момента события.</div>
										<div class="d-flex flex-wrap gap-3 mb-2">
											<label class="form-check smaller mb-0"><input type="checkbox" class="form-check-input" id="input-param-dg-format-0" onchange="prsMethodParamOnBuilderChange(0)"> format</label>
											<label class="form-check smaller mb-0"><input type="checkbox" class="form-check-input" id="input-param-dg-actual-0" onchange="prsMethodParamOnBuilderChange(0)"> actual</label>
										</div>
										<div class="row g-1 mb-1">
											<div class="col-6 col-lg-3"><label class="form-label smaller mb-0 text-muted">start</label><input class="form-control form-control-sm" id="input-param-dg-start-0" placeholder="опционально" oninput="prsMethodParamOnBuilderChange(0)"/></div>
											<div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">maxCount</label><input type="number" class="form-control form-control-sm" id="input-param-dg-maxCount-0" placeholder=" " oninput="prsMethodParamOnBuilderChange(0)"/></div>
											<div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">count</label><input type="number" class="form-control form-control-sm" id="input-param-dg-count-0" oninput="prsMethodParamOnBuilderChange(0)"/></div>
											<div class="col-6 col-lg-2"><label class="form-label smaller mb-0 text-muted">timeStep</label><input type="number" class="form-control form-control-sm" id="input-param-dg-timeStep-0" oninput="prsMethodParamOnBuilderChange(0)"/></div>
										</div>
										<div class="mb-1">
											<label class="form-label smaller mb-0 text-muted">value (строка или JSON)</label>
											<input class="form-control form-control-sm prs-mono" id="input-param-dg-value-0" placeholder="опционально" oninput="prsMethodParamOnBuilderChange(0)"/>
										</div>
										<div class="mb-1">
											<label class="form-label smaller mb-0 text-muted">params (JSON-объект для интеграционных тегов)</label>
											<textarea class="form-control form-control-sm prs-mono" rows="2" id="textarea-param-dg-params-0" placeholder="{}" oninput="prsMethodParamOnBuilderChange(0)"></textarea>
										</div>
										<div class="input-group input-group-sm mt-1">
											<span class="input-group-text smaller text-wrap">URL (без finish)</span>
											<input type="text" readonly class="form-control form-control-sm prs-mono text-truncate" id="input-parameter-dataUrl-preview-0"/>
										</div>
										<div class="d-flex flex-wrap gap-1 mt-1">
											<button type="button" class="btn btn-sm btn-outline-primary" onclick="prsMethodParamTestGet(0)">Пробный запрос</button>
										</div>
										<details class="mt-2 smaller">
											<summary class="user-select-none">JSON (prsJsonConfigString)</summary>
											<textarea class="form-control form-control-sm prs-mono mt-1" rows="5" prsAttribute="parameter" autocomplete="off" id="input-parameter-prsJsonConfigString-0" onchange="onInputChange(event);" onblur="prsMethodParamOnJsonBlur(0)">{}</textarea>
										</details>
										<pre class="smaller bg-white border rounded p-2 mt-1 mb-0 d-none text-break prs-param-dg-test-out" id="pre-parameter-dg-test-0"></pre>
									</div>
								</div>
								<div class="col-auto ms-auto">
									<button type="button" id="but-deleteParameter-0" class="btn btn-sm btn-danger" onclick="deleteParameter(event);" title="Удалить параметр">
										<span><i class="fa-solid fa-minus" id="i-deleteParameter-0"></i></span>
									</button>
								</div>
							</div>'''

OLD_APPEND = r"""$("#div-list-parameters").append(`
      <div class="d-flex align-items-center" prsIndex="${newLevel}" id="span-parameter-${newLevel}">
        <div class="col-1 me-2">
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-${newLevel}"/>
        </div>
        <div class="col-1 me-2">
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-${newLevel}"/>
        </div>
        <div class="col-4 me-2 prs-param-tag-wrap">
          <input type="hidden" id="input-parameter-tagId-${newLevel}" value=""/>
          <div class="input-group input-group-sm">
            <input type="search" class="form-control" id="input-parameter-tagSearch-${newLevel}" placeholder="Поиск тега по имени, пути или id…" autocomplete="off"/>
            <button type="button" class="btn btn-link prs-meth-search-trigger py-0 px-2 align-self-center" id="btn-parameter-tagSearch-${newLevel}" title="Обновить поиск" aria-label="Найти">&#128269;</button>
          </div>
          <div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-${newLevel}"></div>
          <div class="small text-muted mt-1 text-truncate" id="span-parameter-tagPick-${newLevel}">не выбран</div>
        </div>
        <div class="col me-2">
          <!--
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-prsJsonConfigString-${newLevel}"/>
          -->
          <textarea class="form-control form-control-sm" prsAttribute="parameter" autocomplete="off" rows="1" id="input-parameter-prsJsonConfigString-${newLevel}"></textarea>
        </div>
        <button id="but-deleteParameter-${newLevel}" class="btn btn-sm m-1 btn-danger" onclick="deleteParameter(event);">
          <span><i class="fa-solid fa-minus" id="i-deleteParameter-${newLevel}"></i></span>
        </button>
      </div>
    `);"""

NEW_APPEND = r"""$("#div-list-parameters").append(`
      <div class="d-flex flex-wrap align-items-start w-100 border-bottom pb-2 mb-2 prs-method-param-row" prsIndex="${newLevel}" id="span-parameter-${newLevel}">
        <div class="col-6 col-md-1 me-2 mb-1">
          <div class="text-muted smaller mb-0">Индекс</div>
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-${newLevel}"/>
        </div>
        <div class="col-6 col-md-1 me-2 mb-1">
          <div class="text-muted smaller mb-0">Имя</div>
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-${newLevel}"/>
        </div>
        <div class="col-12 col-md-3 me-2 prs-param-tag-wrap mb-1">
          <div class="text-muted smaller mb-0">Тег (источник)</div>
          <input type="hidden" id="input-parameter-tagId-${newLevel}" value=""/>
          <div class="input-group input-group-sm">
            <input type="search" class="form-control" id="input-parameter-tagSearch-${newLevel}" placeholder="Поиск тега…" autocomplete="off"/>
            <button type="button" class="btn btn-outline-secondary btn-sm" id="btn-parameter-tagSearch-${newLevel}" title="Найти">Найти</button>
          </div>
          <div class="prs-method-search-results mt-1 d-none" id="div-parameter-tagResults-${newLevel}"></div>
          <div class="prs-param-tag-pick-label small text-muted mt-1" id="span-parameter-tagPick-${newLevel}">не выбран</div>
        </div>
        <div class="col-12 col-md min-w-0 mb-1 prs-method-param-dg-host">
          <div class="prs-method-param-dg border rounded p-2 bg-light">
            <div class="smaller text-muted mb-2">Тело запроса <code>GET /v1/data/</code>. Платформа подставляет <strong>finish</strong> при запуске.</div>
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
              <label class="form-label smaller mb-0 text-muted">value</label>
              <input class="form-control form-control-sm prs-mono" id="input-param-dg-value-${newLevel}" placeholder="опционально" oninput="prsMethodParamOnBuilderChange(${newLevel})"/>
            </div>
            <div class="mb-1">
              <label class="form-label smaller mb-0 text-muted">params (JSON)</label>
              <textarea class="form-control form-control-sm prs-mono" rows="2" id="textarea-param-dg-params-${newLevel}" placeholder="{}" oninput="prsMethodParamOnBuilderChange(${newLevel})"></textarea>
            </div>
            <div class="input-group input-group-sm mt-1">
              <span class="input-group-text smaller">URL</span>
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
        <div class="col-auto ms-auto">
          <button type="button" id="but-deleteParameter-${newLevel}" class="btn btn-sm btn-danger" onclick="deleteParameter(event);" title="Удалить параметр">
            <span><i class="fa-solid fa-minus" id="i-deleteParameter-${newLevel}"></i></span>
          </button>
        </div>
      </div>
    `);"""

JS_BLOCK = r"""
function prsMethodParamNormalizeConfig(o) {
  if (!o || typeof o !== "object" || Array.isArray(o)) return {};
  var x = {};
  if (o.tagId != null) {
    if (Array.isArray(o.tagId)) x.tagId = o.tagId.map(String).filter(Boolean);
    else x.tagId = [String(o.tagId)];
  }
  if (o.format === true || o.format === "true") x.format = true;
  if (o.actual === true || o.actual === "true") x.actual = true;
  if (o.start != null && String(o.start) !== "") x.start = o.start;
  if (o.maxCount != null && String(o.maxCount) !== "") {
    var mc = Number(o.maxCount);
    if (isFinite(mc)) x.maxCount = mc;
  }
  if (o.count != null && String(o.count) !== "") {
    var c = Number(o.count);
    if (isFinite(c)) x.count = c;
  }
  if (o.timeStep != null && String(o.timeStep) !== "") {
    var ts = Number(o.timeStep);
    if (isFinite(ts)) x.timeStep = ts;
  }
  if (o.value !== undefined) x.value = o.value;
  if (o.params != null && typeof o.params === "object" && !Array.isArray(o.params)) x.params = o.params;
  return x;
}

function prsMethodParamApplyJsonToBuilderFields(level, raw) {
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
}

function prsMethodParamCollectFromBuilder(level) {
  var hid = __prsConfiguratorHtmlNode.getElementById("input-parameter-tagId-" + level);
  var tagId = (hid && hid.value || "").trim();
  var o = {};
  if (tagId) o.tagId = [tagId];
  var fmt = __prsConfiguratorHtmlNode.getElementById("input-param-dg-format-" + level);
  var act = __prsConfiguratorHtmlNode.getElementById("input-param-dg-actual-" + level);
  if (fmt && fmt.checked) o.format = true;
  if (act && act.checked) o.actual = true;
  function numOrEmpty(id) {
    var el = __prsConfiguratorHtmlNode.getElementById(id + level);
    if (!el) return null;
    var s = el.value.trim();
    if (s === "") return null;
    var n = Number(s);
    return isFinite(n) ? n : null;
  }
  var stEl = __prsConfiguratorHtmlNode.getElementById("input-param-dg-start-" + level);
  if (stEl && stEl.value.trim() !== "") o.start = stEl.value.trim();
  var mc = numOrEmpty("input-param-dg-maxCount-");
  if (mc != null) o.maxCount = mc;
  var c = numOrEmpty("input-param-dg-count-");
  if (c != null) o.count = c;
  var tst = numOrEmpty("input-param-dg-timeStep-");
  if (tst != null) o.timeStep = tst;
  var valEl = __prsConfiguratorHtmlNode.getElementById("input-param-dg-value-" + level);
  if (valEl && valEl.value.trim() !== "") {
    var vs = valEl.value.trim();
    try { o.value = JSON.parse(vs); } catch (e1) { o.value = vs; }
  }
  var prm = __prsConfiguratorHtmlNode.getElementById("textarea-param-dg-params-" + level);
  if (prm && prm.value.trim() !== "") {
    try { o.params = JSON.parse(prm.value); } catch (e2) {}
  }
  return prsMethodParamNormalizeConfig(o);
}

function prsMethodParamUpdateUrlPreview(level) {
  var inp = __prsConfiguratorHtmlNode.getElementById("input-parameter-dataUrl-preview-" + level);
  if (!inp) return;
  var ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  var o = {};
  try { o = prsMethodParamNormalizeConfig(JSON.parse(ta && ta.value ? ta.value : "{}")); } catch (e) {
    inp.value = "(некорректный JSON)";
    return;
  }
  inp.value = prsMethodParamBuildDataUrl(o, false);
}

function prsMethodParamBuildDataUrl(obj, includeTestFinish) {
  var base = window.location.protocol + "//" + window.location.hostname + "/v1/data/";
  var p = new URLSearchParams();
  var tags = obj.tagId || [];
  if (!Array.isArray(tags)) tags = [tags];
  tags.forEach(function (tid) { if (tid) p.append("tagId", String(tid)); });
  if (obj.format) p.append("format", "true");
  if (obj.actual) p.append("actual", "true");
  if (obj.maxCount != null) p.append("maxCount", String(obj.maxCount));
  if (obj.count != null) p.append("count", String(obj.count));
  if (obj.timeStep != null) p.append("timeStep", String(obj.timeStep));
  if (obj.start) p.append("start", String(obj.start));
  if (includeTestFinish) {
    p.append("finish", String(Date.now() * 1000));
  }
  if (obj.value !== undefined) {
    p.append("value", typeof obj.value === "string" ? obj.value : JSON.stringify(obj.value));
  }
  if (obj.params != null && typeof obj.params === "object") {
    p.append("params", JSON.stringify(obj.params));
  }
  return base + "?" + p.toString();
}

function prsMethodParamOnBuilderChange(level) {
  var ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  if (!ta) return;
  var o = prsMethodParamCollectFromBuilder(level);
  var jsonStr = JSON.stringify(o, null, "\t");
  ta.value = jsonStr;
  var initv = ta.getAttribute("init-value");
  if (initv != null && jsonStr !== initv) ta.classList.add("value-changed");
  else ta.classList.remove("value-changed");
  prsMethodParamUpdateUrlPreview(level);
  var pre = __prsConfiguratorHtmlNode.getElementById("pre-parameter-dg-test-" + level);
  if (pre) pre.classList.add("d-none");
  prsUpdateSaveResetButtons();
}

function prsMethodParamOnJsonBlur(level) {
  var ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  var pre = __prsConfiguratorHtmlNode.getElementById("pre-parameter-dg-test-" + level);
  if (!ta) return;
  try {
    var o = JSON.parse(ta.value || "{}");
    prsMethodParamApplyJsonToBuilderFields(level, o);
    if (pre) pre.classList.add("d-none");
  } catch (e) {
    if (pre) {
      pre.classList.remove("d-none");
      pre.textContent = "Ошибка JSON: " + e;
    }
  }
}

function prsMethodParamTestGet(level) {
  var ta = __prsConfiguratorHtmlNode.getElementById("input-parameter-prsJsonConfigString-" + level);
  var pre = __prsConfiguratorHtmlNode.getElementById("pre-parameter-dg-test-" + level);
  if (!ta || !pre) return;
  var o;
  try { o = prsMethodParamNormalizeConfig(JSON.parse(ta.value || "{}")); } catch (e1) {
    pre.classList.remove("d-none");
    pre.textContent = "Некорректный JSON: " + e1;
    return;
  }
  if (!o.tagId || !o.tagId.length) {
    pre.classList.remove("d-none");
    pre.textContent = "Укажите тег (tagId).";
    return;
  }
  var url = prsMethodParamBuildDataUrl(o, true);
  pre.classList.remove("d-none");
  pre.textContent = "Запрос…";
  fetch(url, { headers: { "Content-type": "application/json" } })
    .then(function (r) { return r.text().then(function (t) { return { ok: r.ok, status: r.status, t: t }; }); })
    .then(function (res) {
      var head = res.ok ? "OK " + res.status : "HTTP " + res.status;
      var body = res.t;
      if (body.length > 4000) body = body.slice(0, 4000) + "\n…";
      pre.textContent = head + "\n\n" + body;
    })
    .catch(function (err) { pre.textContent = String(err); });
}

function prsMethodParamSetTagPickUI(level, row) {
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
}
"""

def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    html = data["panels"][0]["options"]["html"]
    on = data["panels"][0]["options"]["onRender"]
    css = data["panels"][0]["options"]["css"]

    if OLD_ROW not in html:
        raise SystemExit("OLD_ROW not in html")
    html = html.replace(OLD_ROW, NEW_ROW_0, 1)

    # Tooltip for parameter config column header
    html = html.replace(
        "title='Тело запроса data/get. Полученное значение будет передано методу в качестве значения параметра.'",
        "title='Конфигурация GET /v1/data/ (DataGet): тег, флаги, окно выборки. Ответ API передаётся в метод как значение параметра. finish подставляет платформа.'",
    )

    if OLD_APPEND not in on:
        raise SystemExit("OLD_APPEND not in onRender")
    on = on.replace(OLD_APPEND, NEW_APPEND, 1)

    anchor = "var prsParamSearchTimers = {};\n\nfunction prsPrepareParameterTagPicker"
    if anchor not in on:
        raise SystemExit("anchor not found")
    on = on.replace(anchor, "var prsParamSearchTimers = {};\n" + JS_BLOCK + "\nfunction prsPrepareParameterTagPicker", 1)

    # Replace prsApplyParameterTagPick body (first occurrence only - duplicate in file?)
    old_pick = """function prsApplyParameterTagPick(level, row, silentInit) {
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
  const ta = __prsConfiguratorHtmlNode.querySelector("#input-parameter-prsJsonConfigString-" + level);
  if (ta) {
    const jsonStr = JSON.stringify({ tagId: [row.id] }, null, "\\t");
    $(ta).val(jsonStr);
    if (silentInit) ta.setAttribute("init-value", jsonStr);
    else $(ta).addClass("value-changed");
  }
  if (!silentInit) {
    prsUpdateSaveResetButtons();
  }
}"""

    new_pick = """function prsApplyParameterTagPick(level, row, silentInit) {
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

    cnt = on.count(old_pick)
    if cnt != 1:
        raise SystemExit(f"prsApplyParameterTagPick old block count {cnt}")
    on = on.replace(old_pick, new_pick, 1)

    old_prep = """  if (parameterData) {
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
      if (span) {
        span.className = "prs-param-tag-pick-label small text-muted mt-1";
        span.innerHTML = "";
        var note = document.createElement("div");
        note.className = "prs-pick-saved-note";
        note.textContent = "Сохранённый тег метода (не из поиска инициаторов):";
        span.appendChild(note);
        var meta = document.createElement("div");
        meta.className = "prs-pick-meta";
        meta.textContent = tagId;
        span.appendChild(meta);
      }
    }
  }
}"""

    new_prep = """  if (parameterData) {
    let index = Number(parameterData.attributes.prsIndex[0]);
    let name = parameterData.attributes.cn[0];
    let config_text = parameterData.attributes.prsJsonConfigString[0];
    let config = {};
    try { config = JSON.parse(config_text); } catch (eCfg) { config = {}; }
    if (config && typeof config === "object" && config.data !== undefined && Object.keys(config).length === 1) {
      config = {};
    }
    let tagId;
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
    prsMethodParamUpdateUrlPreview(level);
  }
}"""

    if old_prep not in on:
        raise SystemExit("old_prep not found")
    on = on.replace(old_prep, new_prep, 1)

    # addParameter: after prsPrepareParameterTagPicker(level, data.data, parameterData);
    old_tail = """    level = newLevel;
    prsPrepareParameterTagPicker(level, data.data, parameterData);
  });
}"""
    new_tail = """    level = newLevel;
    prsPrepareParameterTagPicker(level, data.data, parameterData);
    prsMethodParamApplyJsonToBuilderFields(level, {});
    prsMethodParamUpdateUrlPreview(level);
  });
}"""
    if on.count(old_tail) != 1:
        raise SystemExit("addParameter tail count")
    on = on.replace(old_tail, new_tail, 1)

    # deleteParameter: append prsUpdateSaveResetButtons
    old_del = """deleteParameter = (event) => {
  event.stopPropagation();
  targetEl = event.target;
  deletedId = targetEl.id;
  if (deletedId.startsWith("i-"))
    targetEl.parentElement.parentElement.parentElement.remove();
  else
    targetEl.parentElement.remove();
}"""
    new_del = """deleteParameter = (event) => {
  event.stopPropagation();
  targetEl = event.target;
  deletedId = targetEl.id;
  if (deletedId.startsWith("i-"))
    targetEl.parentElement.parentElement.parentElement.remove();
  else
    targetEl.parentElement.remove();
  if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
}"""
    if on.count(old_del) != 1:
        raise SystemExit("deleteParameter count " + str(on.count(old_del)))
    on = on.replace(old_del, new_del, 1)

    # onInputChange: simplify tagId branch — builder sync
    old_oi = """  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    selectedTag = $(targetEl).val();
    payload = {
      tagId: [selectedTag]
    }
    $(`#input-parameter-prsJsonConfigString-${paramIndex}`).val(
      JSON.stringify(payload, null, "\\t")
    ).addClass("value-changed");
  }"""
    new_oi = """  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    var lv = Number(paramIndex);
    if (isFinite(lv)) prsMethodParamOnBuilderChange(lv);
  }"""
    if on.count(old_oi) != 1:
        raise SystemExit("onInputChange tagId branch count " + str(on.count(old_oi)))
    on = on.replace(old_oi, new_oi, 1)

    # expose globals for onclick
    on = on.replace(
        'window.prsFilterParamTagSelect = function (lvl, _q) { if (typeof prsPaintParameterTagResults === "function") prsPaintParameterTagResults(lvl); };',
        'window.prsFilterParamTagSelect = function (lvl, _q) { if (typeof prsPaintParameterTagResults === "function") prsPaintParameterTagResults(lvl); };\n'
        '        window.prsMethodParamOnBuilderChange = prsMethodParamOnBuilderChange;\n'
        '        window.prsMethodParamOnJsonBlur = prsMethodParamOnJsonBlur;\n'
        '        window.prsMethodParamTestGet = prsMethodParamTestGet;',
    )

    css_add = (
        "\\n/* Конструктор DataGet для параметров метода */\\n"
        ".prs-method-param-dg { max-width: 100%; }\\n"
        ".prs-method-param-dg .form-check-input { margin-top: 0.2rem; }\\n"
        ".min-w-0 { min-width: 0; }\\n"
    )
    if ".prs-method-param-dg" not in css:
        css = css + css_add

    data["panels"][0]["options"]["html"] = html
    data["panels"][0]["options"]["onRender"] = on
    data["panels"][0]["options"]["css"] = css

    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Patched", PATH)


if __name__ == "__main__":
    main()
