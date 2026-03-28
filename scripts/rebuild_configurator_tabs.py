#!/usr/bin/env python3
"""Rebuild attributes-form with Bootstrap tabs (panel v2 внутри вкладки «Хранилище»)."""
import json
import re
from pathlib import Path

CFG = Path(__file__).resolve().parents[1] / "src/configurator_grafana/Configurator.json"


def extract_outer_div_by_id(html: str, div_id: str) -> tuple[str | None, str]:
    """Удаляет первый <div id="...">...</div> с точным id, возвращает (блок, html без блока)."""
    pat = rf'<div[^>]*\bid="{re.escape(div_id)}"[^>]*>'
    m = re.search(pat, html)
    if not m:
        return None, html
    start = m.start()
    i = m.end()
    depth = 1
    while i < len(html) and depth:
        if html.startswith("<div", i):
            depth += 1
            i = html.find(">", i) + 1
            continue
        if html.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                return html[start:i], html[:start] + html[i:]
        else:
            i += 1
    return None, html


def extract_attributes_form_inner(html: str) -> tuple[str | None, int, int]:
    """Возвращает inner HTML между <div id="attributes-form"...> и закрывающим </div>."""
    af = html.find('id="attributes-form"')
    if af < 0:
        return None, -1, -1
    open_end = html.find(">", af) + 1
    inner_region = html[open_end:]
    depth = 1
    i = 0
    close_start = None
    while i < len(inner_region):
        if inner_region.startswith("<div", i):
            depth += 1
            i = inner_region.find(">", i) + 1
            continue
        if inner_region.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                close_start = i - 6
                break
        else:
            i += 1
    if close_start is None:
        return None, -1, -1
    return inner_region[:close_start], open_end, open_end + close_start


def extract_div_block(s: str, div_id: str):
    pat = rf'<div[^>]*\bid="{re.escape(div_id)}"[^>]*>'
    m = re.search(pat, s)
    if not m:
        return None, s
    start = m.start()
    rest = s[start:]
    depth = 0
    i = 0
    while i < len(rest):
        if rest.startswith("<div", i):
            depth += 1
            i = rest.find(">", i) + 1
            continue
        if rest.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                end = start + i
                return s[start:end], s[:start] + s[end:]
        else:
            i += 1
    return None, s


LINKAGE_SELECTS = """
			<div class="input-group mt-2" id="div-prsTagDataStorageLink">
				<span class="input-group-text prs-input-label space-between">Хранилище данных
						<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip" title="Одна привязка на тег. Смена хранилища отвязывает от предыдущего."></i>
					</span>
				<select class="form-select" id="select-prsTagLinkedStorage">
					<option value="">— не привязан —</option>
				</select>
			</div>
			<div class="input-group mt-2" id="div-prsTagConnectorLink">
				<span class="input-group-text prs-input-label space-between">Коннектор
						<i class="fa-solid fa-circle-info gray" data-bs-toggle="tooltip" title="Одна привязка на тег. Смена коннектора отвязывает от предыдущего."></i>
					</span>
				<select class="form-select" id="select-prsTagLinkedConnector">
					<option value="">— не привязан —</option>
				</select>
			</div>
"""


def ensure_linkage_selects(html: str) -> str:
    """Убирает старый drop-zone, вставляет селекторы привязки (если их ещё нет)."""
    if "id=\"div-prsTagDataStorageLink\"" in html:
        return html
    drop, html2 = extract_outer_div_by_id(html, "div-prsDataStorageDrop")
    if drop:
        html = html2
    needle = '<div class="input-group mt-2" id="div-prsMethodAddress"'
    pos = html.find(needle)
    if pos < 0:
        raise SystemExit("div-prsMethodAddress block not found for linkage insert")
    return html[:pos] + LINKAGE_SELECTS + "\n\t\t\t" + html[pos:]


def main():
    data = json.loads(CFG.read_text(encoding="utf-8"))
    html = data["panels"][0]["options"]["html"]
    html = ensure_linkage_selects(html)

    panel_full, html_wo = extract_outer_div_by_id(html, "prs-ds-linked-tag-panel")
    if not panel_full:
        raise SystemExit("prs-ds-linked-tag-panel not found")

    inner, open_end, inner_end = extract_attributes_form_inner(html_wo)
    if inner is None:
        raise SystemExit("attributes-form inner parse failed")

    cn_idx = inner.find('id="div-cn"')
    if cn_idx < 0:
        raise SystemExit("div-cn in inner")
    # header: до начала тега <div> с id="div-cn", чтобы не обрезать разметку
    cn_tag_start = inner.rfind("<div", 0, cn_idx)
    if cn_tag_start < 0:
        raise SystemExit("div-cn opening tag not found in inner")
    header = inner[:cn_tag_start]

    stor, inner2 = extract_div_block(inner, "div-prsTagDataStorageLink")
    conn, inner3 = extract_div_block(inner2, "div-prsTagConnectorLink")
    tagd, inner4 = extract_div_block(inner3, "div-tagData")
    if not stor or not conn or not tagd:
        raise SystemExit("extract storage/connector/tagData failed")

    up = inner4.find('id="div-updateAlert"')
    if up < 0:
        raise SystemExit("div-updateAlert")
    cn4 = inner4.find('id="div-cn"')
    if cn4 < 0:
        raise SystemExit("div-cn in inner4")
    # props_only и footer: с начала полного тега <div>, чтобы не выводить обрезанный HTML
    props_start = inner4.rfind("<div", 0, cn4)
    alert_start = inner4.rfind("<div", 0, up)
    if props_start < 0 or alert_start < 0:
        raise SystemExit("div-cn or div-updateAlert opening tag not found in inner4")
    props_only = inner4[props_start:up]
    footer = inner4[alert_start:]

    panel_block = panel_full.strip()
    panel_block = panel_block.replace(
        'class="p-2 d-none flex-shrink-0 border-top mt-3 prs-linked-tag-panel"',
        'class="p-2 d-none prs-linked-tag-panel border rounded mt-2"',
    )
    panel_block = panel_block.replace(
        'class="p-2 d-none flex-shrink-0 border-bottom"',
        'class="p-2 d-none prs-linked-tag-panel border rounded mt-2"',
    )

    tabs_top = """
			<div id="prs-form-normal-wrap">
			<ul class="nav nav-tabs nav-tabs-sm mb-2 flex-nowrap flex-shrink-0" id="prs-form-tabs" role="tablist">
				<li class="nav-item" role="presentation">
					<button class="nav-link active" id="prs-tab-trigger-props" data-bs-toggle="tab" data-bs-target="#prs-tab-pane-props" type="button" role="tab" aria-controls="prs-tab-pane-props" aria-selected="true">Свойства</button>
				</li>
				<li class="nav-item d-none" id="prs-tab-li-storage" role="presentation">
					<button class="nav-link" id="prs-tab-trigger-storage" data-bs-toggle="tab" data-bs-target="#prs-tab-pane-storage" type="button" role="tab" aria-controls="prs-tab-pane-storage" aria-selected="false">Хранилище</button>
				</li>
				<li class="nav-item d-none" id="prs-tab-li-connector" role="presentation">
					<button class="nav-link" id="prs-tab-trigger-connector" data-bs-toggle="tab" data-bs-target="#prs-tab-pane-connector" type="button" role="tab" aria-controls="prs-tab-pane-connector" aria-selected="false">Коннектор</button>
				</li>
			</ul>
			<div class="tab-content" id="prs-form-tab-content">
				<div class="tab-pane fade show active" id="prs-tab-pane-props" role="tabpanel" aria-labelledby="prs-tab-trigger-props" tabindex="0">
"""

    storage_pane_mid = (
        """
				</div>
				<div class="tab-pane fade" id="prs-tab-pane-storage" role="tabpanel" aria-labelledby="prs-tab-trigger-storage" tabindex="0">
					<div id="prs-storage-tag-only" class="d-none">
"""
        + stor
        + '\n\t\t\t<div id="prs-storage-v2-host" class="mb-2"></div>\n'
        + tagd
        + """
					</div>
					<div id="prs-storage-alert-only" class="d-none">
						<p class="text-muted smaller mb-0">Привязка тревоги к хранилищу данных настраивается в дереве «Хранилища данных» → выберите хранилище → привязанная тревога. Здесь можно будет задать параметры привязки, когда они появятся в форме.</p>
					</div>
				</div>
				<div class="tab-pane fade" id="prs-tab-pane-connector" role="tabpanel" aria-labelledby="prs-tab-trigger-connector" tabindex="0">
"""
        + conn
        + """
				</div>
			</div>
"""
    )

    new_inner = (
        header
        + tabs_top
        + props_only
        + storage_pane_mid
        + "\n"
        + footer
        + "\n\t\t\t</div>\n\t\t\t"
        + '<div id="prs-ds-linked-tag-panel-tree-slot" class="d-none">'
        + panel_block
        + "</div>\n\t\t"
    )

    html_out = html_wo[:open_end] + new_inner + "</div>" + html_wo[inner_end:]

    data["panels"][0]["options"]["html"] = html_out
    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK, html length", len(html_out))


if __name__ == "__main__":
    main()
